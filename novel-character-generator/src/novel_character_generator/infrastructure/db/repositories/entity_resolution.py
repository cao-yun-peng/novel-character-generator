from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.entity_resolution import (
    EntityConvergenceResult,
    EntityMemoryRecord,
    GroundedCandidatePacket,
)
from novel_character_generator.domain.policies.grounding import observation_fingerprint
from novel_character_generator.domain.policies.visual_fields import (
    normalize_life_phase,
    normalize_observation_fields,
)
from novel_character_generator.infrastructure.db.orm import (
    ChapterORM,
    CharacterConvergenceBatchORM,
    CharacterORM,
    CharacterResolutionChunkORM,
    FeatureObservationORM,
    MentionSpanORM,
    NormalizationMapORM,
    PipelineRunORM,
    SourceDocumentVersionORM,
    TemporalSignalORM,
    TextChunkORM,
    TimelineORM,
)


class EntityResolutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def stable_memory(self, novel_id: UUID) -> list[EntityMemoryRecord]:
        characters = list(
            await self.session.scalars(
                select(CharacterORM)
                .where(
                    CharacterORM.novel_id == novel_id,
                    CharacterORM.merged_into_character_id.is_(None),
                )
                .order_by(CharacterORM.created_at, CharacterORM.id)
            )
        )
        return [
            EntityMemoryRecord(
                memory_id=f"character:{character.id}",
                character_id=character.id,
                canonical_name=character.canonical_name,
                status="stable",
                names=[character.canonical_name],
                explicit_names=[character.canonical_name],
                last_chunk_ordinal=0,
            )
            for character in characters
        ]

    async def chunk_record(
        self, run_id: UUID, chunk_id: UUID
    ) -> CharacterResolutionChunkORM | None:
        return cast(
            CharacterResolutionChunkORM | None,
            await self.session.scalar(
                select(CharacterResolutionChunkORM).where(
                    CharacterResolutionChunkORM.run_id == run_id,
                    CharacterResolutionChunkORM.source_chunk_id == chunk_id,
                )
            ),
        )

    async def save_extracted_candidates(
        self,
        *,
        run: PipelineRunORM,
        chunk: TextChunkORM,
        document: SourceDocumentVersionORM,
        normalization_map: NormalizationMapORM,
        extraction_result: dict[str, object],
        packet: GroundedCandidatePacket,
        provider_raw_response: object | None = None,
        provider_raw_message_content: object | None = None,
    ) -> CharacterResolutionChunkORM:
        existing = await self.chunk_record(run.id, chunk.id)
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        spans_by_mention_id: dict[str, MentionSpanORM] = {}
        for mention in packet.mentions:
            span = await self.session.scalar(
                select(MentionSpanORM).where(
                    MentionSpanORM.source_chunk_id == chunk.id,
                    MentionSpanORM.char_start == mention.start,
                    MentionSpanORM.char_end == mention.end,
                    MentionSpanORM.mention_text == mention.mention_text,
                    MentionSpanORM.mention_kind == mention.mention_kind,
                )
            )
            if span is None:
                span = MentionSpanORM(
                    id=uuid4(),
                    source_document_version=str(document.version),
                    source_document_version_id=document.id,
                    source_chunk_id=chunk.id,
                    char_start=mention.start,
                    char_end=mention.end,
                    mention_text=mention.mention_text,
                    mention_kind=mention.mention_kind,
                    candidate_character_ids=[],
                    resolved_character_id=None,
                    grounding_status="exact",
                    normalization_map_version=normalization_map.algorithm_version,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(span)
            spans_by_mention_id[mention.mention_id] = span
        await self.session.flush()
        for signal in packet.temporal_signals:
            fingerprint = sha256(f"{run.id}:{chunk.id}:{signal.signal_id}".encode()).hexdigest()
            existing_signal = await self.session.scalar(
                select(TemporalSignalORM.id).where(TemporalSignalORM.fingerprint == fingerprint)
            )
            if existing_signal is not None:
                continue
            span = (
                spans_by_mention_id.get(signal.mention_id)
                if signal.mention_id is not None
                else None
            )
            self.session.add(
                TemporalSignalORM(
                    id=uuid4(),
                    run_id=run.id,
                    source_document_version_id=document.id,
                    source_chunk_id=chunk.id,
                    mention_span_id=span.id if span is not None else None,
                    character_id=None,
                    feature_observation_ids=[],
                    signal_id=signal.signal_id,
                    fact_candidate_key=signal.fact_candidate_key,
                    kind=signal.kind,
                    label=signal.label,
                    evidence_quote=signal.evidence_quote,
                    char_start=signal.start,
                    char_end=signal.end,
                    grounding_status="exact",
                    confidence=signal.confidence,
                    resolution_status="candidate",
                    fingerprint=fingerprint,
                    created_at=now,
                    updated_at=now,
                )
            )
        record = CharacterResolutionChunkORM(
            id=uuid4(),
            run_id=run.id,
            source_chunk_id=chunk.id,
            chunk_ordinal=chunk.ordinal,
            extraction_result=extraction_result,
            candidate_packet=packet.model_dump(mode="json"),
            provider_raw_response=provider_raw_response,
            provider_raw_message_content=provider_raw_message_content,
            provider_raw_response_hash=json_payload_hash(provider_raw_response),
            resolver_raw_response=None,
            resolver_raw_message_content=None,
            resolver_raw_response_hash=None,
            resolution_input_hash=None,
            resolution_result=None,
            memory_after=None,
            resolver_version=None,
            context_truncated=False,
            status="extracted",
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def resolved_chunks(
        self, run_id: UUID, *, start: int | None = None, end: int | None = None
    ) -> list[CharacterResolutionChunkORM]:
        query = select(CharacterResolutionChunkORM).where(
            CharacterResolutionChunkORM.run_id == run_id,
            CharacterResolutionChunkORM.status == "resolved",
        )
        if start is not None:
            query = query.where(CharacterResolutionChunkORM.chunk_ordinal >= start)
        if end is not None:
            query = query.where(CharacterResolutionChunkORM.chunk_ordinal <= end)
        return list(
            await self.session.scalars(query.order_by(CharacterResolutionChunkORM.chunk_ordinal))
        )

    async def convergence_batch(
        self, run_id: UUID, batch_index: int
    ) -> CharacterConvergenceBatchORM | None:
        return cast(
            CharacterConvergenceBatchORM | None,
            await self.session.scalar(
                select(CharacterConvergenceBatchORM).where(
                    CharacterConvergenceBatchORM.run_id == run_id,
                    CharacterConvergenceBatchORM.batch_index == batch_index,
                )
            ),
        )

    async def completed_batches(self, run_id: UUID) -> list[CharacterConvergenceBatchORM]:
        return list(
            await self.session.scalars(
                select(CharacterConvergenceBatchORM)
                .where(
                    CharacterConvergenceBatchORM.run_id == run_id,
                    CharacterConvergenceBatchORM.status.in_(
                        ("completed", "completed_with_warnings")
                    ),
                )
                .order_by(CharacterConvergenceBatchORM.batch_index)
            )
        )

    async def create_convergence_batch(
        self,
        *,
        run_id: UUID,
        batch_index: int,
        start: int,
        end: int,
        final_batch: bool,
        input_hash: str,
        resolver_version: str,
    ) -> CharacterConvergenceBatchORM:
        existing = await self.convergence_batch(run_id, batch_index)
        if existing is not None:
            if existing.input_hash != input_hash:
                raise RuntimeError("entity_convergence_input_changed")
            return existing
        now = datetime.now(UTC)
        row = CharacterConvergenceBatchORM(
            id=uuid4(),
            run_id=run_id,
            batch_index=batch_index,
            start_chunk_ordinal=start,
            end_chunk_ordinal=end,
            final_batch=final_batch,
            input_hash=input_hash,
            result=None,
            memory_after=None,
            resolver_raw_response=None,
            resolver_raw_message_content=None,
            resolver_raw_response_hash=None,
            resolver_version=resolver_version,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def materialize_convergence(
        self,
        *,
        run: PipelineRunORM,
        document: SourceDocumentVersionORM,
        timeline: TimelineORM,
        result: EntityConvergenceResult,
        memory: list[EntityMemoryRecord],
        extractor_version: str,
        resolver_version: str,
    ) -> tuple[list[EntityMemoryRecord], dict[str, str]]:
        rows = list(
            await self.session.scalars(
                select(CharacterResolutionChunkORM).where(
                    CharacterResolutionChunkORM.run_id == run.id
                )
            )
        )
        mention_catalog: dict[str, tuple[GroundedCandidatePacket, TextChunkORM, int | None]] = {}
        for row in rows:
            packet = GroundedCandidatePacket.model_validate(row.candidate_packet)
            chunk = await self.session.get(TextChunkORM, row.source_chunk_id)
            if chunk is None:
                raise RuntimeError("entity_resolution_chunk_missing")
            chapter_ordinal: int | None = None
            if chunk.chapter_id is not None:
                chapter = await self.session.get(ChapterORM, chunk.chapter_id)
                chapter_ordinal = chapter.ordinal if chapter is not None else None
            for mention in packet.mentions:
                mention_catalog[mention.mention_id] = (packet, chunk, chapter_ordinal)

        created_by_key: dict[str, CharacterORM] = {}
        bindings: dict[str, CharacterORM] = {}
        run_observations = list(
            await self.session.scalars(
                select(FeatureObservationORM).where(
                    FeatureObservationORM.extraction_run_id == run.id,
                    FeatureObservationORM.record_status.in_(("pending", "active")),
                )
            )
        )
        now = datetime.now(UTC)
        for decision in result.decisions:
            character: CharacterORM | None = None
            if decision.action == "confirm_link":
                character = await self.session.get(CharacterORM, decision.target_character_id)
                if character is None or character.novel_id != run.novel_id:
                    raise ValueError("entity_convergence_foreign_character")
            elif decision.action in {"create_character", "split_candidate"}:
                assert decision.creation_key is not None
                character = created_by_key.get(decision.creation_key)
                if character is None:
                    character = CharacterORM(
                        id=uuid4(),
                        novel_id=run.novel_id,
                        canonical_name=decision.canonical_name,
                        status="candidate",
                        revision=1,
                        merged_into_character_id=None,
                        created_at=now,
                        updated_at=now,
                    )
                    self.session.add(character)
                    created_by_key[decision.creation_key] = character
            if character is not None:
                for mention_id in decision.mention_ids:
                    bindings[mention_id] = character
        await self.session.flush()

        version = f"{extractor_version}|{resolver_version}"
        for mention_id, character in bindings.items():
            packet, chunk, chapter_ordinal = mention_catalog[mention_id]
            mention = next(item for item in packet.mentions if item.mention_id == mention_id)
            span = await self.session.scalar(
                select(MentionSpanORM).where(
                    MentionSpanORM.source_chunk_id == chunk.id,
                    MentionSpanORM.char_start == mention.start,
                    MentionSpanORM.char_end == mention.end,
                    MentionSpanORM.mention_text == mention.mention_text,
                    MentionSpanORM.mention_kind == mention.mention_kind,
                )
            )
            if span is None:
                raise RuntimeError("entity_resolution_mention_span_missing")
            span.candidate_character_ids = [str(character.id)]
            span.resolved_character_id = character.id
            span.updated_at = now
            mention_signals = list(
                await self.session.scalars(
                    select(TemporalSignalORM).where(
                        TemporalSignalORM.run_id == run.id,
                        TemporalSignalORM.mention_span_id == span.id,
                    )
                )
            )
            for signal in mention_signals:
                signal.character_id = character.id
                signal.resolution_status = "bound"
                signal.updated_at = now
            for fact in (item for item in packet.facts if item.mention_id == mention_id):
                life_phase_key, life_phase_label = normalize_life_phase(
                    fact.life_phase_key, fact.life_phase_label
                )
                fact_observation_ids: list[str] = []
                for normalized in normalize_observation_fields(
                    fact.field_path,
                    fact.value,
                    character_name=character.canonical_name,
                    evidence_quote=fact.evidence_quote,
                ):
                    duplicate = next(
                        (
                            item
                            for item in run_observations
                            if item.character_id == character.id
                            and item.source_chunk_id == chunk.id
                            and item.field_path == normalized.field_path
                            and json.dumps(
                                item.value,
                                ensure_ascii=False,
                                sort_keys=True,
                                default=str,
                            )
                            == json.dumps(
                                normalized.value,
                                ensure_ascii=False,
                                sort_keys=True,
                                default=str,
                            )
                            and item.char_start is not None
                            and item.char_end is not None
                            and max(item.char_start, fact.start) < min(item.char_end, fact.end)
                        ),
                        None,
                    )
                    fingerprint = observation_fingerprint(
                        source_version=f"{document.source_document_id}:{document.version}",
                        start=chunk.normalized_char_start + fact.start,
                        end=chunk.normalized_char_start + fact.end,
                        field_path=normalized.field_path,
                        value=normalized.value,
                        extractor_version=version,
                    )
                    observation_id = duplicate.id if duplicate is not None else None
                    if observation_id is None:
                        observation_id = await self.session.scalar(
                            select(FeatureObservationORM.id).where(
                                FeatureObservationORM.fingerprint == fingerprint
                            )
                        )
                    if observation_id is None:
                        observation_id = uuid4()
                        temporal_scope: dict[str, object] = {
                            "timeline_id": str(timeline.id),
                            "scope_type": "unknown",
                            "start_chapter_ordinal": chapter_ordinal,
                            "presentation_mode": "direct",
                            "reality_status": "canonical",
                            "scope_resolution_status": "provisional",
                        }
                        if life_phase_key is not None:
                            temporal_scope["life_phase_key"] = life_phase_key
                        if life_phase_label is not None:
                            temporal_scope["life_phase_label"] = life_phase_label
                        observation = FeatureObservationORM(
                            id=observation_id,
                            character_id=character.id,
                            field_path=normalized.field_path,
                            value=normalized.value,
                            source_kind="text",
                            source_document_version_id=document.id,
                            source_chunk_id=chunk.id,
                            mention_span_id=span.id,
                            evidence_quote=fact.evidence_quote,
                            char_start=fact.start,
                            char_end=fact.end,
                            chapter_ordinal=chapter_ordinal,
                            scene_id=None,
                            event_id=None,
                            temporal_scope=temporal_scope,
                            epistemic_status=fact.epistemic_status,
                            grounding_status="exact",
                            confidence=fact.confidence,
                            extraction_run_id=run.id,
                            manual_approval_id=None,
                            extractor_version=version,
                            supersedes_id=None,
                            fingerprint=fingerprint,
                            valid_from=now,
                            valid_to=None,
                            record_status="pending",
                            recorded_at=None,
                            invalidated_at=None,
                            invalidated_by_run_id=None,
                            created_at=now,
                            updated_at=now,
                        )
                        self.session.add(observation)
                        run_observations.append(observation)
                    fact_observation_ids.append(str(observation_id))
                if fact.candidate_key is not None and fact_observation_ids:
                    fact_signals = [
                        signal
                        for signal in mention_signals
                        if signal.fact_candidate_key == fact.candidate_key
                    ]
                    for signal in fact_signals:
                        signal.feature_observation_ids = list(
                            dict.fromkeys([*signal.feature_observation_ids, *fact_observation_ids])
                        )

        updated_memory: list[EntityMemoryRecord] = []
        for record in memory:
            bound = next(
                (
                    bindings[mention_id]
                    for mention_id in record.mention_ids
                    if mention_id in bindings
                ),
                None,
            )
            if bound is not None:
                updated_memory.append(
                    record.model_copy(
                        update={
                            "memory_id": f"character:{bound.id}",
                            "character_id": bound.id,
                            "canonical_name": bound.canonical_name,
                            "status": "stable",
                            "names": list(dict.fromkeys([*record.names, bound.canonical_name])),
                            "explicit_names": list(
                                dict.fromkeys([*record.explicit_names, bound.canonical_name])
                            ),
                        }
                    )
                )
            else:
                rejected = any(
                    decision.action == "reject_candidate"
                    and set(decision.mention_ids) & set(record.mention_ids)
                    for decision in result.decisions
                )
                if not rejected:
                    updated_memory.append(record)
        deduplicated: dict[str, EntityMemoryRecord] = {}
        for record in updated_memory:
            if record.status == "stable" and len(record.mention_ids) > 64:
                record = record.model_copy(update={"mention_ids": record.mention_ids[-64:]})
            prior = deduplicated.get(record.memory_id)
            if prior is None:
                deduplicated[record.memory_id] = record
            else:
                merged_mentions = list(dict.fromkeys([*prior.mention_ids, *record.mention_ids]))
                if prior.status == "stable":
                    merged_mentions = merged_mentions[-64:]
                deduplicated[record.memory_id] = prior.model_copy(
                    update={
                        "mention_ids": merged_mentions,
                        "names": list(dict.fromkeys([*prior.names, *record.names])),
                        "explicit_names": list(
                            dict.fromkeys([*prior.explicit_names, *record.explicit_names])
                        ),
                        "evidence_quotes": list(
                            dict.fromkeys([*prior.evidence_quotes, *record.evidence_quotes])
                        )[:64],
                        "last_chunk_ordinal": max(
                            prior.last_chunk_ordinal, record.last_chunk_ordinal
                        ),
                    }
                )
        await self.session.flush()
        return list(deduplicated.values()), {
            key: str(value.id) for key, value in created_by_key.items()
        }


def stable_json_hash(value: BaseModel) -> str:
    return sha256(value.model_dump_json(exclude_none=True).encode("utf-8")).hexdigest()


def json_payload_hash(value: object | None) -> str | None:
    if value is None:
        return None
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
