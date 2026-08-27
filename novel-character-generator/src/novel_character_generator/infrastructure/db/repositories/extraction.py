from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.extraction import (
    GroundedVisualExtractionResult,
    ObservationDraft,
)
from novel_character_generator.domain.policies.grounding import (
    GroundingStatus,
    observation_fingerprint,
    repair_evidence_span,
    validate_evidence,
)
from novel_character_generator.domain.policies.visual_fields import (
    normalize_life_phase,
    normalize_observation_fields,
)
from novel_character_generator.infrastructure.db.orm import (
    ChapterORM,
    CharacterORM,
    CharacterRelationORM,
    FeatureObservationORM,
    MentionSpanORM,
    NormalizationMapORM,
    PipelineRunORM,
    SourceDocumentORM,
    SourceDocumentVersionORM,
    TextChunkORM,
    TimelineORM,
)


class ExtractionRepository:
    """Persist the grounded visual output of the v3 extraction pipeline."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def chunks(self, novel_id: UUID) -> list[TextChunkORM]:
        result = await self.session.scalars(
            select(TextChunkORM)
            .join(
                SourceDocumentORM,
                TextChunkORM.source_document_version_id == SourceDocumentORM.current_version_id,
            )
            .where(SourceDocumentORM.novel_id == novel_id)
            .order_by(TextChunkORM.ordinal)
        )
        return list(result)

    async def source_document(self, novel_id: UUID) -> SourceDocumentVersionORM:
        document = await self.session.scalar(
            select(SourceDocumentVersionORM)
            .join(
                SourceDocumentORM,
                SourceDocumentVersionORM.id == SourceDocumentORM.current_version_id,
            )
            .where(SourceDocumentORM.novel_id == novel_id)
            .order_by(SourceDocumentORM.created_at.desc())
        )
        if document is None:
            raise RuntimeError("source_document_not_found")
        return document

    async def normalization_map(self, document_version_id: UUID) -> NormalizationMapORM:
        normalization_map = await self.session.scalar(
            select(NormalizationMapORM).where(
                NormalizationMapORM.source_document_version_id == document_version_id
            )
        )
        if normalization_map is None:
            raise RuntimeError("normalization_map_not_found")
        return normalization_map

    async def canonical_timeline(self, novel_id: UUID) -> TimelineORM:
        timeline = await self.session.scalar(
            select(TimelineORM).where(
                TimelineORM.novel_id == novel_id,
                TimelineORM.canonicality == "canonical",
            )
        )
        if timeline is None:
            timeline = TimelineORM(
                id=uuid4(),
                novel_id=novel_id,
                name="主时间线",
                parent_timeline_id=None,
                branch_event_id=None,
                canonicality="canonical",
            )
            self.session.add(timeline)
            await self.session.flush()
        return timeline

    async def supersede_prior_extractor_observations(
        self,
        *,
        run: PipelineRunORM,
        document: SourceDocumentVersionORM,
        extractor_version: str,
    ) -> None:
        """Replace prior automatic truth while retaining historical rows for audit."""

        now = datetime.now(UTC)
        await self.session.execute(
            update(FeatureObservationORM)
            .where(
                FeatureObservationORM.source_document_version_id == document.id,
                FeatureObservationORM.source_kind == "text",
                FeatureObservationORM.record_status == "active",
                FeatureObservationORM.extraction_run_id.is_not(None),
                FeatureObservationORM.extraction_run_id != run.id,
                FeatureObservationORM.extractor_version != extractor_version,
            )
            .values(
                record_status="superseded",
                valid_to=now,
                invalidated_at=now,
                invalidated_by_run_id=run.id,
                updated_at=now,
            )
        )
        # Relations produced by the removed joint extractor are historical-only after v3.
        await self.session.execute(
            update(CharacterRelationORM)
            .where(
                CharacterRelationORM.source_document_version_id == document.id,
                CharacterRelationORM.record_status == "active",
                CharacterRelationORM.extraction_run_id != run.id,
                CharacterRelationORM.extractor_version != extractor_version,
            )
            .values(record_status="superseded", updated_at=now)
        )

    async def supersede_all_prior_automatic_observations(
        self,
        *,
        run: PipelineRunORM,
        document: SourceDocumentVersionORM,
    ) -> None:
        """Replace prior truth after a recoverable run used multiple resolver versions."""

        now = datetime.now(UTC)
        await self.session.execute(
            update(FeatureObservationORM)
            .where(
                FeatureObservationORM.source_document_version_id == document.id,
                FeatureObservationORM.source_kind == "text",
                FeatureObservationORM.record_status == "active",
                FeatureObservationORM.extraction_run_id.is_not(None),
                FeatureObservationORM.extraction_run_id != run.id,
            )
            .values(
                record_status="superseded",
                valid_to=now,
                invalidated_at=now,
                invalidated_by_run_id=run.id,
                updated_at=now,
            )
        )
        await self.session.execute(
            update(CharacterRelationORM)
            .where(
                CharacterRelationORM.source_document_version_id == document.id,
                CharacterRelationORM.record_status == "active",
                CharacterRelationORM.extraction_run_id != run.id,
            )
            .values(record_status="superseded", updated_at=now)
        )

    async def activate_run_observations(self, *, run: PipelineRunORM) -> None:
        """Publish visual observations only after every chunk has succeeded."""

        now = datetime.now(UTC)
        await self.session.execute(
            update(FeatureObservationORM)
            .where(
                FeatureObservationORM.extraction_run_id == run.id,
                FeatureObservationORM.record_status == "pending",
            )
            .values(record_status="active", recorded_at=now, updated_at=now)
        )

    async def get_or_create_character(self, novel_id: UUID, name: str) -> CharacterORM:
        character = await self.session.scalar(
            select(CharacterORM).where(
                CharacterORM.novel_id == novel_id,
                CharacterORM.canonical_name == name,
            )
        )
        if character is None:
            now = datetime.now(UTC)
            character = CharacterORM(
                id=uuid4(),
                novel_id=novel_id,
                canonical_name=name,
                status="candidate",
                created_at=now,
                updated_at=now,
            )
            self.session.add(character)
            await self.session.flush()
        return character

    async def persist_result(
        self,
        *,
        run: PipelineRunORM,
        chunk: TextChunkORM,
        document: SourceDocumentVersionORM,
        normalization_map: NormalizationMapORM,
        timeline: TimelineORM,
        result: GroundedVisualExtractionResult,
        extractor_version: str,
    ) -> None:
        # R2 deliberately forbids this legacy direct materialization path. It is
        # retained temporarily as a typed compatibility surface for diagnostics,
        # but production extraction must persist candidates and pass convergence.
        raise RuntimeError("direct_visual_materialization_forbidden")

        # The unreachable implementation below documents the former v3 behavior
        # until the legacy GroundedVisualExtractionResult DTO is removed.
        now = datetime.now(UTC)
        chapter_ordinal: int | None = None
        if chunk.chapter_id is not None:
            chapter = await self.session.get(ChapterORM, chunk.chapter_id)
            chapter_ordinal = chapter.ordinal if chapter is not None else None

        prepared_observations: list[tuple[ObservationDraft, GroundingStatus]] = []
        for observation in result.observations:
            start, end, grounding = repair_evidence_span(
                chunk.content,
                observation.evidence_quote,
                observation.start,
                observation.end,
            )
            life_phase_key, life_phase_label = normalize_life_phase(
                observation.life_phase_key,
                observation.life_phase_label,
            )
            for fact in normalize_observation_fields(
                observation.field_path,
                observation.value,
                character_name=observation.character_name,
                evidence_quote=observation.evidence_quote,
            ):
                prepared_observations.append(
                    (
                        observation.model_copy(
                            update={
                                "field_path": fact.field_path,
                                "value": fact.value,
                                "start": start,
                                "end": end,
                                "life_phase_key": life_phase_key,
                                "life_phase_label": life_phase_label,
                            }
                        ),
                        grounding,
                    )
                )

        requested_names = {
            *(mention.canonical_name for mention in result.mentions if mention.canonical_name),
            *(observation.character_name for observation, _ in prepared_observations),
        }
        characters = {
            name: await self.get_or_create_character(run.novel_id, name)
            for name in sorted(requested_names)
        }
        character_ids = {character.id for character in characters.values()}
        reincarnation_character_ids = {
            character.id
            for observation, _ in prepared_observations
            if observation.life_phase_key in {"past_life", "reincarnated_childhood"}
            if (character := characters.get(observation.character_name)) is not None
        }
        if character_ids:
            existing_scopes = await self.session.execute(
                select(
                    FeatureObservationORM.character_id,
                    FeatureObservationORM.temporal_scope,
                ).where(
                    FeatureObservationORM.character_id.in_(character_ids),
                    FeatureObservationORM.record_status.in_(("active", "pending")),
                )
            )
            reincarnation_character_ids.update(
                character_id
                for character_id, scope in existing_scopes
                if (scope or {}).get("life_phase_key") in {"past_life", "reincarnated_childhood"}
            )

        adjusted_observations: list[tuple[ObservationDraft, GroundingStatus]] = []
        for observation, grounding in prepared_observations:
            character = characters.get(observation.character_name)
            updates: dict[str, object] = {}
            if (
                observation.field_path in {"identity.experienced_age", "identity.mental_age_stage"}
                and observation.life_phase_key == "adulthood"
            ):
                updates.update(life_phase_key=None, life_phase_label=None)
            elif (
                character is not None
                and character.id in reincarnation_character_ids
                and observation.life_phase_key == "childhood"
            ):
                updates.update(
                    life_phase_key="reincarnated_childhood",
                    life_phase_label="转生幼年",
                )
            adjusted_observations.append(
                (observation.model_copy(update=updates) if updates else observation, grounding)
            )

        mentions_by_character: dict[str, MentionSpanORM] = {}
        for mention in result.mentions:
            grounding = validate_evidence(chunk.content, mention.text, mention.start, mention.end)
            resolved = characters.get(mention.canonical_name or "")
            span = await self.session.scalar(
                select(MentionSpanORM).where(
                    MentionSpanORM.source_chunk_id == chunk.id,
                    MentionSpanORM.char_start == mention.start,
                    MentionSpanORM.char_end == mention.end,
                    MentionSpanORM.mention_text == mention.text,
                    MentionSpanORM.mention_kind == mention.kind,
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
                    mention_text=mention.text,
                    mention_kind=mention.kind,
                    candidate_character_ids=[str(resolved.id)] if resolved else [],
                    resolved_character_id=(
                        resolved.id if grounding == "exact" and resolved else None
                    ),
                    grounding_status=grounding,
                    normalization_map_version=normalization_map.algorithm_version,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(span)
            if mention.canonical_name:
                mentions_by_character[mention.canonical_name] = span
        await self.session.flush()

        for observation, grounding in adjusted_observations:
            absolute_start = chunk.normalized_char_start + observation.start
            absolute_end = chunk.normalized_char_start + observation.end
            fingerprint = observation_fingerprint(
                source_version=f"{document.source_document_id}:{document.version}",
                start=absolute_start,
                end=absolute_end,
                field_path=observation.field_path,
                value=observation.value,
                extractor_version=extractor_version,
            )
            exists = await self.session.scalar(
                select(FeatureObservationORM.id).where(
                    FeatureObservationORM.fingerprint == fingerprint
                )
            )
            if exists is not None:
                continue
            character = characters[observation.character_name]
            temporal_scope: dict[str, object] = {
                "timeline_id": str(timeline.id),
                "scope_type": "unknown",
                "start_chapter_ordinal": chapter_ordinal,
                "presentation_mode": "direct",
                "reality_status": "canonical",
            }
            if observation.life_phase_key is not None:
                temporal_scope["life_phase_key"] = observation.life_phase_key
            if observation.life_phase_label is not None:
                temporal_scope["life_phase_label"] = observation.life_phase_label
            owner_span = mentions_by_character.get(observation.character_name)
            self.session.add(
                FeatureObservationORM(
                    id=uuid4(),
                    character_id=character.id,
                    field_path=observation.field_path,
                    value=observation.value,
                    source_kind="text",
                    source_document_version_id=document.id,
                    source_chunk_id=chunk.id,
                    mention_span_id=owner_span.id if owner_span is not None else None,
                    evidence_quote=observation.evidence_quote,
                    char_start=observation.start,
                    char_end=observation.end,
                    chapter_ordinal=chapter_ordinal,
                    scene_id=None,
                    event_id=None,
                    temporal_scope=temporal_scope,
                    epistemic_status=observation.epistemic_status,
                    grounding_status=grounding,
                    confidence=observation.confidence,
                    extraction_run_id=run.id,
                    manual_approval_id=None,
                    extractor_version=extractor_version,
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
            )
        await self.session.flush()
