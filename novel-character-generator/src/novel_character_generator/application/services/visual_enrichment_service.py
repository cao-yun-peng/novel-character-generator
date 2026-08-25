from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.visual_enrichment import (
    VisualEnrichmentResult,
    VisualEvidencePacket,
    VisualEvidencePassage,
)
from novel_character_generator.application.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from novel_character_generator.domain.entities.retrieval import RetrievalHit
from novel_character_generator.domain.policies.grounding import (
    observation_fingerprint,
    repair_evidence_span,
    validate_evidence,
)
from novel_character_generator.domain.policies.visual_fields import (
    canonical_field_path,
    is_visual_field,
    normalize_life_phase,
)
from novel_character_generator.domain.policies.visual_query_plan import (
    CORE_FIELD_GROUPS,
    FIELD_GAP_POLICY_VERSION,
    FIELD_GROUPS,
    QUERY_PLAN_VERSION,
    build_visual_query_plan,
    visual_field_group,
)
from novel_character_generator.infrastructure.db.orm import (
    AliasAssertionORM,
    CharacterORM,
    FeatureObservationORM,
    FeatureSuggestionORM,
    HumanApprovalORM,
    PipelineRunORM,
    PipelineStepORM,
    RetrievalIndexBuildORM,
    RetrievalPassageChunkSpanORM,
    RetrievalPassageORM,
    RetrievalQueryHitORM,
    RetrievalQueryRunORM,
    SourceDocumentORM,
    SourceDocumentVersionORM,
    TextChunkORM,
    VisualEnrichmentRejectionORM,
)
from novel_character_generator.infrastructure.db.repositories.retrieval import (
    RetrievalRepository,
)
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event


@dataclass(frozen=True)
class PersistVisualEvidenceOutcome:
    observation_ids: list[UUID]
    suggestion_ids: list[UUID]
    rejected_count: int


@dataclass(frozen=True)
class VisualFieldGroupGap:
    field_group: str
    covered: bool
    priority: str
    observed_field_paths: list[str]


@dataclass(frozen=True)
class VisualFieldGapPlan:
    character_id: UUID
    source_document_version_id: UUID
    retrieval_index_build_id: UUID | None
    retrieval_index_status: str
    life_phase_key: str | None
    available_life_phases: list[dict[str, str]]
    groups: list[VisualFieldGroupGap]
    recommended_field_groups: list[str]
    policy_version: str


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


class VisualEnrichmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.retrieval_repository = RetrievalRepository(session)

    async def create_run(
        self,
        *,
        character_id: UUID,
        field_groups: list[str],
        life_phase_key: str | None,
        max_provider_calls: int,
        context_budget_tokens: int,
        idempotency_key: str,
        auto_plan: bool = False,
    ) -> PipelineRunORM:
        character = await self.session.get(CharacterORM, character_id)
        if character is None or character.merged_into_character_id is not None:
            raise ValueError("character_not_found")
        source = await self._current_source(character.novel_id)
        if source is None:
            raise ValueError("source_document_not_found")
        build = await self.retrieval_repository.latest_build_for_source(source.id)
        if build is None or build.status != "ready":
            raise RuntimeError("retrieval_index_not_ready")
        auto_planned = auto_plan and not field_groups
        if auto_planned:
            gap_plan = await self.field_gap_plan(
                character_id=character.id, life_phase_key=life_phase_key
            )
            field_groups = gap_plan.recommended_field_groups
            if not field_groups:
                raise RuntimeError("visual_field_gaps_empty")
        validated_plan = build_visual_query_plan(
            canonical_name=character.canonical_name,
            aliases=[],
            field_groups=field_groups,
            life_phase_key=life_phase_key,
            max_provider_calls=max_provider_calls,
            context_budget_tokens=context_budget_tokens,
        )
        field_groups = list(validated_plan.field_groups)
        life_phase_key = validated_plan.life_phase_key
        request_payload = {
            "character_id": str(character.id),
            "source_document_version_id": str(source.id),
            "retrieval_index_build_id": str(build.id),
            "field_groups": field_groups,
            "life_phase_key": life_phase_key,
            "max_provider_calls": max_provider_calls,
            "context_budget_tokens": context_budget_tokens,
            "auto_planned": auto_planned,
            "field_gap_policy_version": FIELD_GAP_POLICY_VERSION,
        }
        request_hash = _canonical_hash(request_payload)
        existing = await self.session.scalar(
            select(PipelineRunORM).where(PipelineRunORM.idempotency_key == idempotency_key)
        )
        if existing is not None:
            step = await self.session.scalar(
                select(PipelineStepORM).where(
                    PipelineStepORM.run_id == existing.id,
                    PipelineStepORM.step_key == "plan_visual_retrieval",
                )
            )
            if (
                existing.run_type != "visual_enrichment"
                or step is None
                or (step.cursor or {}).get("request_hash") != request_hash
            ):
                raise RuntimeError("idempotency_key_payload_conflict")
            return existing
        now = datetime.now(UTC)
        run = PipelineRunORM(
            id=uuid4(),
            novel_id=character.novel_id,
            run_type="visual_enrichment",
            status="queued",
            idempotency_key=idempotency_key,
            cancel_requested=False,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        step = PipelineStepORM(
            id=uuid4(),
            run_id=run.id,
            step_key="plan_visual_retrieval",
            status="queued",
            attempt=0,
            lease_owner=None,
            lease_expires_at=None,
            lease_generation=0,
            heartbeat_at=None,
            next_attempt_at=None,
            cursor={"schema_version": "v1", "request_hash": request_hash, **request_payload},
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add_all([run, step])
        await self.session.flush()
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="run.created",
            payload={
                "run_type": run.run_type,
                "step_key": step.step_key,
                "character_id": str(character.id),
                "request_hash": request_hash,
            },
        )
        await self.session.commit()
        return run

    async def field_gap_plan(
        self, *, character_id: UUID, life_phase_key: str | None
    ) -> VisualFieldGapPlan:
        character = await self.session.get(CharacterORM, character_id)
        if character is None or character.merged_into_character_id is not None:
            raise ValueError("character_not_found")
        source = await self._current_source(character.novel_id)
        if source is None:
            raise ValueError("source_document_not_found")
        build = await self.retrieval_repository.latest_build_for_source(source.id)
        normalized_phase = life_phase_key.strip() if life_phase_key else None
        rows = list(
            await self.session.scalars(
                select(FeatureObservationORM).where(
                    FeatureObservationORM.character_id == character.id,
                    FeatureObservationORM.source_document_version_id == source.id,
                    FeatureObservationORM.record_status == "active",
                    FeatureObservationORM.valid_to.is_(None),
                    FeatureObservationORM.epistemic_status == "asserted",
                    FeatureObservationORM.grounding_status.in_(("exact", "manually_grounded")),
                )
            )
        )
        phases: dict[str, str] = {}
        covered_paths: dict[str, set[str]] = {group: set() for group in FIELD_GROUPS}
        for row in rows:
            scope = row.temporal_scope or {}
            row_phase = scope.get("life_phase_key")
            row_label = scope.get("life_phase_label")
            if row_phase:
                phases[str(row_phase)] = str(row_label or row_phase)
            if normalized_phase and row_phase not in {None, normalized_phase}:
                continue
            group = visual_field_group(canonical_field_path(row.field_path))
            if group is not None:
                covered_paths[group].add(canonical_field_path(row.field_path))
        groups = [
            VisualFieldGroupGap(
                field_group=group,
                covered=bool(covered_paths[group]),
                priority="core" if group in CORE_FIELD_GROUPS else "optional",
                observed_field_paths=sorted(covered_paths[group]),
            )
            for group in FIELD_GROUPS
        ]
        recommended = [item.field_group for item in groups if not item.covered]
        return VisualFieldGapPlan(
            character_id=character.id,
            source_document_version_id=source.id,
            retrieval_index_build_id=build.id if build else None,
            retrieval_index_status=build.status if build else "missing",
            life_phase_key=normalized_phase,
            available_life_phases=[
                {"key": key, "label": label} for key, label in sorted(phases.items())
            ],
            groups=groups,
            recommended_field_groups=recommended,
            policy_version=FIELD_GAP_POLICY_VERSION,
        )

    async def plan(self, run: PipelineRunORM, cursor: dict[str, object]) -> RetrievalQueryRunORM:
        character_id = UUID(str(cursor["character_id"]))
        character = await self.session.get(CharacterORM, character_id)
        if character is None or character.novel_id != run.novel_id:
            raise ValueError("character_not_found")
        build_id = UUID(str(cursor["retrieval_index_build_id"]))
        build = await self.retrieval_repository.get_build(build_id)
        if build is None or build.status != "ready":
            raise ValueError("retrieval_index_not_ready")
        aliases = list(
            await self.session.scalars(
                select(AliasAssertionORM.alias_text)
                .where(
                    AliasAssertionORM.proposed_character_id == character.id,
                    AliasAssertionORM.status.in_(("accepted", "approved")),
                )
                .order_by(AliasAssertionORM.alias_text)
            )
        )
        raw_field_groups = cursor["field_groups"]
        if not isinstance(raw_field_groups, list):
            raise RuntimeError("visual_field_groups_invalid")
        field_groups = [str(item) for item in raw_field_groups]
        plan = build_visual_query_plan(
            canonical_name=character.canonical_name,
            aliases=aliases,
            field_groups=field_groups,
            life_phase_key=(
                str(cursor["life_phase_key"]) if cursor.get("life_phase_key") else None
            ),
            max_provider_calls=int(str(cursor["max_provider_calls"])),
            context_budget_tokens=int(str(cursor["context_budget_tokens"])),
        )
        existing = await self.session.scalar(
            select(RetrievalQueryRunORM).where(
                RetrievalQueryRunORM.enrichment_run_id == run.id,
                RetrievalQueryRunORM.query_plan_hash == plan.fingerprint,
            )
        )
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        query_run = RetrievalQueryRunORM(
            id=uuid4(),
            enrichment_run_id=run.id,
            retrieval_index_build_id=build.id,
            character_id=character.id,
            life_phase_key=plan.life_phase_key,
            field_groups=list(plan.field_groups),
            query_plan=plan.as_dict(),
            query_plan_hash=plan.fingerprint,
            lexical_profile_version=build.lexical_profile_version,
            embedding_profile_version=build.embedding_profile_version,
            created_at=now,
            updated_at=now,
        )
        self.session.add(query_run)
        await self.session.flush()
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="visual_enrichment.planned",
            payload={
                "query_run_id": str(query_run.id),
                "query_plan_hash": plan.fingerprint,
                "query_plan_version": QUERY_PLAN_VERSION,
                "query_count": len(plan.queries),
                "field_groups": list(plan.field_groups),
            },
        )
        return query_run

    async def retrieve(
        self,
        *,
        run: PipelineRunORM,
        query_run: RetrievalQueryRunORM,
        retrieval: HybridRetrievalService,
        bm25_top_k: int,
        vector_top_k: int,
        rrf_k: int,
        main_hit_limit: int,
        neighbor_count: int,
    ) -> VisualEvidencePacket:
        plan = query_run.query_plan
        queries = plan.get("queries")
        if not isinstance(queries, list):
            raise RuntimeError("visual_query_plan_invalid")
        entity_terms = [str(item) for item in plan.get("entity_terms", [])]
        merged: dict[UUID, RetrievalHit] = {}
        passage_rows: dict[UUID, RetrievalPassageORM] = {}
        for query in queries:
            if not isinstance(query, dict) or not isinstance(query.get("text"), str):
                raise RuntimeError("visual_query_plan_invalid")
            result = await retrieval.retrieve(
                build_id=query_run.retrieval_index_build_id,
                query_text=query["text"],
                entity_terms=entity_terms,
                bm25_top_k=bm25_top_k,
                vector_top_k=vector_top_k,
                rrf_k=rrf_k,
                main_hit_limit=main_hit_limit,
                neighbor_count=neighbor_count,
            )
            passage_rows.update({row.id: row for row in result.packet_passages})
            for hit in result.hits:
                current = merged.get(hit.passage_id)
                if current is None:
                    merged[hit.passage_id] = hit
                    continue
                channels = tuple(dict.fromkeys((*current.source_channels, *hit.source_channels)))
                merged[hit.passage_id] = RetrievalHit(
                    passage_id=hit.passage_id,
                    source_channels=channels,
                    bm25_score=max(
                        (item for item in (current.bm25_score, hit.bm25_score) if item is not None),
                        default=None,
                    ),
                    vector_score=max(
                        (
                            item
                            for item in (current.vector_score, hit.vector_score)
                            if item is not None
                        ),
                        default=None,
                    ),
                    bm25_rank=min(
                        (item for item in (current.bm25_rank, hit.bm25_rank) if item is not None),
                        default=None,
                    ),
                    vector_rank=min(
                        (
                            item
                            for item in (current.vector_rank, hit.vector_rank)
                            if item is not None
                        ),
                        default=None,
                    ),
                    rrf_score=current.rrf_score + hit.rrf_score,
                    exact_entity_match=current.exact_entity_match or hit.exact_entity_match,
                    expansion_reason=current.expansion_reason or hit.expansion_reason,
                    final_rank=0,
                    selected=True,
                )
        ranked = sorted(
            merged.values(),
            key=lambda hit: (-hit.rrf_score, not hit.exact_entity_match, str(hit.passage_id)),
        )
        hits = [
            RetrievalHit(**{**hit.__dict__, "final_rank": rank})
            for rank, hit in enumerate(ranked, start=1)
        ]
        await self.retrieval_repository.record_query_hits(
            retrieval_query_run_id=query_run.id, hits=hits
        )
        budget = int(plan.get("context_budget_tokens", 8_000))
        selected: list[RetrievalPassageORM] = []
        used_tokens = 0
        for passage in sorted(passage_rows.values(), key=lambda row: row.ordinal):
            if selected and used_tokens + passage.token_count > budget:
                continue
            selected.append(passage)
            used_tokens += passage.token_count
        character = await self.session.get_one(CharacterORM, query_run.character_id)
        packet = VisualEvidencePacket(
            character_id=character.id,
            canonical_name=character.canonical_name,
            aliases=[str(item) for item in plan.get("aliases", [])],
            field_groups=query_run.field_groups,
            life_phase_key=query_run.life_phase_key,
            passages=[
                VisualEvidencePassage(
                    passage_id=row.id,
                    chapter_ordinal=row.chapter_ordinal,
                    ordinal=row.ordinal,
                    previous_passage_id=row.previous_passage_id,
                    next_passage_id=row.next_passage_id,
                    content=row.content,
                )
                for row in selected
            ],
        )
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="visual_enrichment.retrieved",
            payload={
                "query_run_id": str(query_run.id),
                "hit_count": len(hits),
                "selected_passage_count": len(selected),
            },
        )
        await self.session.flush()
        return packet

    async def packet_for_query(self, query_run: RetrievalQueryRunORM) -> VisualEvidencePacket:
        hits = list(
            await self.session.scalars(
                select(RetrievalQueryHitORM)
                .where(
                    RetrievalQueryHitORM.retrieval_query_run_id == query_run.id,
                    RetrievalQueryHitORM.selected.is_(True),
                )
                .order_by(RetrievalQueryHitORM.final_rank)
            )
        )
        passages = await self.retrieval_repository.get_passages(
            [hit.retrieval_passage_id for hit in hits]
        )
        plan = query_run.query_plan
        budget = int(plan.get("context_budget_tokens", 8_000))
        selected: list[RetrievalPassageORM] = []
        used = 0
        for row in sorted(passages.values(), key=lambda passage: passage.ordinal):
            if selected and used + row.token_count > budget:
                continue
            selected.append(row)
            used += row.token_count
        character = await self.session.get_one(CharacterORM, query_run.character_id)
        return VisualEvidencePacket(
            character_id=character.id,
            canonical_name=character.canonical_name,
            aliases=[str(item) for item in plan.get("aliases", [])],
            field_groups=query_run.field_groups,
            life_phase_key=query_run.life_phase_key,
            passages=[
                VisualEvidencePassage(
                    passage_id=row.id,
                    chapter_ordinal=row.chapter_ordinal,
                    ordinal=row.ordinal,
                    previous_passage_id=row.previous_passage_id,
                    next_passage_id=row.next_passage_id,
                    content=row.content,
                )
                for row in selected
            ],
        )

    async def persist_result(
        self,
        *,
        run: PipelineRunORM,
        query_run: RetrievalQueryRunORM,
        result: VisualEnrichmentResult,
        extractor_version: str,
    ) -> PersistVisualEvidenceOutcome:
        build = await self.session.get_one(
            RetrievalIndexBuildORM, query_run.retrieval_index_build_id
        )
        source = await self.session.get_one(
            SourceDocumentVersionORM, build.source_document_version_id
        )
        passage_map = await self.retrieval_repository.get_passages(
            list(dict.fromkeys(item.retrieval_passage_id for item in result.observations))
        )
        now = datetime.now(UTC)
        observation_ids: list[UUID] = []
        suggestion_ids: list[UUID] = []
        rejected = 0
        rejection_reason_counts: dict[str, int] = {}
        for draft in result.observations:
            passage = passage_map.get(draft.retrieval_passage_id)
            field_path = canonical_field_path(draft.field_path)
            rejection_reasons: list[str] = []
            repaired_start: int | None = None
            repaired_end: int | None = None
            if passage is None:
                rejection_reasons.append("retrieval_passage_not_found")
            elif passage.retrieval_index_build_id != build.id:
                rejection_reasons.append("retrieval_passage_wrong_index")
            else:
                repaired_start, repaired_end, grounding = repair_evidence_span(
                    passage.content, draft.evidence_quote, draft.start, draft.end
                )
                if grounding != "exact":
                    rejection_reasons.append(f"evidence_{grounding}")
            if not is_visual_field(field_path):
                rejection_reasons.append("field_not_visual")
            if rejection_reasons:
                rejection_id = uuid4()
                self.session.add(
                    VisualEnrichmentRejectionORM(
                        id=rejection_id,
                        enrichment_run_id=run.id,
                        retrieval_query_run_id=query_run.id,
                        character_id=query_run.character_id,
                        retrieval_passage_id=passage.id if passage is not None else None,
                        field_path=field_path,
                        value=draft.value,
                        evidence_quote=draft.evidence_quote,
                        requested_start=draft.start,
                        requested_end=draft.end,
                        repaired_start=repaired_start,
                        repaired_end=repaired_end,
                        reason_codes=rejection_reasons,
                        draft=draft.model_dump(mode="json"),
                        created_at=now,
                        updated_at=now,
                    )
                )
                for reason in rejection_reasons:
                    rejection_reason_counts[reason] = (
                        rejection_reason_counts.get(reason, 0) + 1
                    )
                rejected += 1
                continue
            assert passage is not None
            assert repaired_start is not None and repaired_end is not None
            mapped = await self._map_exact_span(
                passage_id=passage.id,
                passage_start=repaired_start,
                passage_end=repaired_end,
                quote=draft.evidence_quote,
            )
            direct_fact = (
                draft.character_id == query_run.character_id
                and draft.evidence_kind == "direct"
                and draft.epistemic_status == "asserted"
                and mapped is not None
            )
            phase_key, phase_label = normalize_life_phase(
                draft.life_phase_key or query_run.life_phase_key, draft.life_phase_label
            )
            if direct_fact and mapped is not None:
                chunk, chunk_start, chunk_end = mapped
                fingerprint = observation_fingerprint(
                    source_version=f"{source.source_document_id}:{source.version}",
                    start=chunk.normalized_char_start + chunk_start,
                    end=chunk.normalized_char_start + chunk_end,
                    field_path=field_path,
                    value=draft.value,
                    extractor_version=extractor_version,
                )
                existing_id = await self.session.scalar(
                    select(FeatureObservationORM.id).where(
                        FeatureObservationORM.fingerprint == fingerprint
                    )
                )
                if existing_id is not None:
                    observation_ids.append(existing_id)
                    continue
                temporal_scope: dict[str, object] = {
                    "scope_type": "unknown",
                    "start_chapter_ordinal": passage.chapter_ordinal,
                    "presentation_mode": "direct",
                    "reality_status": "canonical",
                }
                if phase_key:
                    temporal_scope["life_phase_key"] = phase_key
                if phase_label:
                    temporal_scope["life_phase_label"] = phase_label
                observation_id = uuid4()
                self.session.add(
                    FeatureObservationORM(
                        id=observation_id,
                        character_id=query_run.character_id,
                        field_path=field_path,
                        value=draft.value,
                        source_kind="retrieval_text",
                        source_document_version_id=source.id,
                        source_chunk_id=chunk.id,
                        retrieval_passage_id=passage.id,
                        mention_span_id=None,
                        evidence_quote=draft.evidence_quote,
                        char_start=chunk_start,
                        char_end=chunk_end,
                        chapter_ordinal=passage.chapter_ordinal,
                        scene_id=None,
                        event_id=None,
                        temporal_scope=temporal_scope,
                        epistemic_status="asserted",
                        grounding_status="exact",
                        confidence=draft.confidence,
                        extraction_run_id=run.id,
                        manual_approval_id=None,
                        extractor_version=extractor_version,
                        supersedes_id=None,
                        fingerprint=fingerprint,
                        valid_from=now,
                        valid_to=None,
                        record_status="active",
                        recorded_at=now,
                        invalidated_at=None,
                        invalidated_by_run_id=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                observation_ids.append(observation_id)
                continue
            suggestion_id = uuid4()
            reason_codes = []
            if draft.character_id != query_run.character_id:
                reason_codes.append("character_unresolved")
            if draft.epistemic_status != "asserted":
                reason_codes.append(f"epistemic:{draft.epistemic_status}")
            if draft.evidence_kind != "direct":
                reason_codes.append(f"evidence:{draft.evidence_kind}")
            if mapped is None:
                reason_codes.append("chunk_mapping_not_unique")
            self.session.add(
                FeatureSuggestionORM(
                    id=suggestion_id,
                    character_id=query_run.character_id,
                    field_path=field_path,
                    value=draft.value,
                    suggestion_kind="visual_evidence_candidate",
                    resource_version=extractor_version,
                    confidence=draft.confidence,
                    allowed_fields=[field_path],
                    rationale=",".join(reason_codes) or "manual_review_required",
                    status="candidate",
                    approval_id=None,
                    source_document_version_id=source.id,
                    enrichment_run_id=run.id,
                    evidence_links=[
                        {
                            "retrieval_passage_id": str(passage.id),
                            "start": repaired_start,
                            "end": repaired_end,
                            "quote": draft.evidence_quote,
                            "evidence_kind": draft.evidence_kind,
                            "epistemic_status": draft.epistemic_status,
                        }
                    ],
                    provenance_version=VISUAL_EVIDENCE_PROVENANCE_VERSION,
                    created_at=now,
                    updated_at=now,
                )
            )
            suggestion_ids.append(suggestion_id)
        await self.session.flush()
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="visual_enrichment.evidence_persisted",
            payload={
                "observation_count": len(observation_ids),
                "suggestion_count": len(suggestion_ids),
                "rejected_count": rejected,
                "rejection_reason_counts": rejection_reason_counts,
                "extractor_version": extractor_version,
            },
        )
        if suggestion_ids:
            await append_run_event(
                self.session,
                run_id=run.id,
                event_type="visual_enrichment.suggested",
                payload={"suggestion_count": len(suggestion_ids)},
            )
        return PersistVisualEvidenceOutcome(observation_ids, suggestion_ids, rejected)

    async def resolve_suggestion(
        self, *, suggestion_id: UUID, decision: str, actor_id: str
    ) -> FeatureSuggestionORM:
        suggestion = await self.session.get(FeatureSuggestionORM, suggestion_id)
        if suggestion is None:
            raise ValueError("feature_suggestion_not_found")
        if suggestion.status != "candidate":
            raise RuntimeError("feature_suggestion_already_resolved")
        if decision not in {"accept", "reject"}:
            raise ValueError("feature_suggestion_decision_invalid")
        now = datetime.now(UTC)
        action = {
            "decision": decision,
            "suggestion_id": str(suggestion.id),
            "field_path": suggestion.field_path,
            "value": suggestion.value,
        }
        approval = HumanApprovalORM(
            id=uuid4(),
            pipeline_step_id=None,
            requested_by_agent_run_id=None,
            approval_type="feature_suggestion",
            subject_type="feature_suggestion",
            subject_id=suggestion.id,
            lease_generation=0,
            revision=1,
            action_hash=_canonical_hash(action),
            action=action,
            supporting_evidence_ids=[],
            opposing_evidence_ids=[],
            estimated_cost=None,
            status="approved" if decision == "accept" else "rejected",
            decision="approve" if decision == "accept" else "reject",
            modifications=None,
            resolved_by=actor_id,
            expires_at=now + timedelta(days=3650),
            resolved_at=now,
            recovery_token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
            decision_payload_hash=_canonical_hash({"decision": decision}),
            created_at=now,
            updated_at=now,
        )
        self.session.add(approval)
        await self.session.flush()
        suggestion.status = "accepted" if decision == "accept" else "rejected"
        suggestion.approval_id = approval.id
        suggestion.updated_at = now
        await self.session.commit()
        return suggestion

    async def _current_source(self, novel_id: UUID) -> SourceDocumentVersionORM | None:
        return cast(
            SourceDocumentVersionORM | None,
            await self.session.scalar(
                select(SourceDocumentVersionORM)
                .join(
                    SourceDocumentORM,
                    SourceDocumentVersionORM.id == SourceDocumentORM.current_version_id,
                )
                .where(SourceDocumentORM.novel_id == novel_id)
                .order_by(SourceDocumentORM.created_at.desc())
                .limit(1)
            ),
        )

    async def _map_exact_span(
        self, *, passage_id: UUID, passage_start: int, passage_end: int, quote: str
    ) -> tuple[TextChunkORM, int, int] | None:
        rows = list(
            await self.session.scalars(
                select(RetrievalPassageChunkSpanORM).where(
                    RetrievalPassageChunkSpanORM.retrieval_passage_id == passage_id,
                    RetrievalPassageChunkSpanORM.passage_char_start <= passage_start,
                    RetrievalPassageChunkSpanORM.passage_char_end >= passage_end,
                )
            )
        )
        if len(rows) != 1:
            return None
        span = rows[0]
        chunk = await self.session.get(TextChunkORM, span.source_chunk_id)
        if chunk is None:
            return None
        chunk_start = span.chunk_char_start + passage_start - span.passage_char_start
        chunk_end = span.chunk_char_start + passage_end - span.passage_char_start
        if validate_evidence(chunk.content, quote, chunk_start, chunk_end) != "exact":
            return None
        return chunk, chunk_start, chunk_end


VISUAL_EVIDENCE_PROVENANCE_VERSION = "visual-evidence-provenance-v1"
