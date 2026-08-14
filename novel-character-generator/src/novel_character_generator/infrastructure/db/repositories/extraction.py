from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.extraction import ChunkExtractionResult
from novel_character_generator.domain.policies.grounding import (
    observation_fingerprint,
    validate_evidence,
)
from novel_character_generator.infrastructure.db.orm import (
    AliasAssertionORM,
    CharacterORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    MentionSpanORM,
    PipelineRunORM,
    SourceDocumentORM,
    TextChunkORM,
    TimelineORM,
)


class ExtractionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def chunks(self, novel_id: UUID) -> list[TextChunkORM]:
        result = await self.session.scalars(
            select(TextChunkORM)
            .where(TextChunkORM.novel_id == novel_id)
            .order_by(TextChunkORM.ordinal)
        )
        return list(result)

    async def source_document(self, novel_id: UUID) -> SourceDocumentORM:
        document = await self.session.scalar(
            select(SourceDocumentORM)
            .where(SourceDocumentORM.novel_id == novel_id)
            .order_by(SourceDocumentORM.created_at.desc())
        )
        if document is None:
            raise RuntimeError("source_document_not_found")
        return cast(SourceDocumentORM, document)

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
        return cast(TimelineORM, timeline)

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
        return cast(CharacterORM, character)

    async def persist_result(
        self,
        *,
        run: PipelineRunORM,
        chunk: TextChunkORM,
        document: SourceDocumentORM,
        timeline: TimelineORM,
        result: ChunkExtractionResult,
        extractor_version: str,
    ) -> None:
        now = datetime.now(UTC)
        characters: dict[str, CharacterORM] = {}
        for mention in result.mentions:
            if mention.canonical_name:
                characters[mention.canonical_name] = await self.get_or_create_character(
                    run.novel_id, mention.canonical_name
                )
        for observation in result.observations:
            characters[observation.character_name] = await self.get_or_create_character(
                run.novel_id, observation.character_name
            )
        for expression in result.expression_observations:
            characters[expression.character_name] = await self.get_or_create_character(
                run.novel_id, expression.character_name
            )

        mentions_by_span: dict[tuple[int, int], MentionSpanORM] = {}
        for mention in result.mentions:
            grounding = validate_evidence(chunk.content, mention.text, mention.start, mention.end)
            resolved = characters.get(mention.canonical_name or "")
            span = MentionSpanORM(
                id=uuid4(),
                source_document_version=document.version,
                source_chunk_id=chunk.id,
                char_start=mention.start,
                char_end=mention.end,
                mention_text=mention.text,
                mention_kind=mention.kind,
                candidate_character_ids=[str(resolved.id)] if resolved else [],
                resolved_character_id=resolved.id if grounding == "exact" and resolved else None,
                grounding_status=grounding,
                normalization_map_version=document.normalization_map_version or "unknown",
                created_at=now,
                updated_at=now,
            )
            self.session.add(span)
            mentions_by_span[(mention.start, mention.end)] = span
        await self.session.flush()

        for alias in result.alias_hypotheses:
            span = mentions_by_span.get((alias.mention_start, alias.mention_end))
            if span is None:
                grounding = validate_evidence(
                    chunk.content, alias.alias_text, alias.mention_start, alias.mention_end
                )
                owner = characters.get(alias.canonical_name or "")
                span = MentionSpanORM(
                    id=uuid4(),
                    source_document_version=document.version,
                    source_chunk_id=chunk.id,
                    char_start=alias.mention_start,
                    char_end=alias.mention_end,
                    mention_text=alias.alias_text,
                    mention_kind=alias.alias_kind,
                    candidate_character_ids=[str(owner.id)] if owner else [],
                    resolved_character_id=None,
                    grounding_status=grounding,
                    normalization_map_version=document.normalization_map_version or "unknown",
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(span)
                await self.session.flush()
            owner = characters.get(alias.canonical_name or "")
            self.session.add(
                AliasAssertionORM(
                    id=uuid4(),
                    alias_text=alias.alias_text,
                    alias_kind=alias.alias_kind,
                    normalized_alias=alias.alias_text.casefold(),
                    mention_span_id=span.id,
                    proposed_character_id=owner.id if owner else None,
                    speaker_id=None,
                    scene_id=None,
                    timeline_id=timeline.id,
                    supporting_evidence_ids=[str(span.id)],
                    opposing_evidence_ids=[],
                    status="proposed",
                    created_at=now,
                    updated_at=now,
                )
            )

        for observation in result.observations:
            grounding = validate_evidence(
                chunk.content, observation.evidence_quote, observation.start, observation.end
            )
            absolute_start = chunk.normalized_char_start + observation.start
            absolute_end = chunk.normalized_char_start + observation.end
            fingerprint = observation_fingerprint(
                source_version=document.version,
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
            self.session.add(
                FeatureObservationORM(
                    id=uuid4(),
                    character_id=character.id,
                    field_path=observation.field_path,
                    value=observation.value,
                    source_kind="text",
                    source_chunk_id=chunk.id,
                    evidence_quote=observation.evidence_quote,
                    char_start=observation.start,
                    char_end=observation.end,
                    chapter_ordinal=None,
                    scene_id=None,
                    event_id=None,
                    temporal_scope={
                        "timeline_id": str(timeline.id),
                        "scope_type": "unknown",
                        "presentation_mode": "direct",
                        "reality_status": "canonical",
                    },
                    epistemic_status=observation.epistemic_status,
                    grounding_status=grounding,
                    confidence=observation.confidence,
                    extraction_run_id=run.id,
                    extractor_version=extractor_version,
                    supersedes_id=None,
                    fingerprint=fingerprint,
                    valid_from=now,
                    valid_to=None,
                    created_at=now,
                    updated_at=now,
                )
            )

        for expression in result.expression_observations:
            grounding = validate_evidence(
                chunk.content, expression.expression_text, expression.start, expression.end
            )
            if grounding == "ungrounded":
                continue
            fingerprint = observation_fingerprint(
                source_version=document.version,
                start=chunk.normalized_char_start + expression.start,
                end=chunk.normalized_char_start + expression.end,
                field_path="expression.outward_emotion",
                value=expression.outward_emotion,
                extractor_version=extractor_version,
            )
            exists = await self.session.scalar(
                select(ExpressionObservationORM.id).where(
                    ExpressionObservationORM.fingerprint == fingerprint
                )
            )
            if exists is not None:
                continue
            character = characters[expression.character_name]
            self.session.add(
                ExpressionObservationORM(
                    id=uuid4(),
                    character_id=character.id,
                    source_chunk_id=chunk.id,
                    char_start=expression.start,
                    char_end=expression.end,
                    outward_emotion=expression.outward_emotion,
                    expression_text=expression.expression_text,
                    visible_cues=expression.visible_cues,
                    intensity=None,
                    valence=None,
                    arousal=None,
                    is_masked=None,
                    internal_emotion=expression.internal_emotion,
                    target_character_id=None,
                    cause_event_id=None,
                    scene_id=None,
                    temporal_scope={
                        "timeline_id": str(timeline.id),
                        "scope_type": "instant",
                        "presentation_mode": "direct",
                        "reality_status": "canonical",
                    },
                    evidence_quote=expression.expression_text,
                    epistemic_status="asserted",
                    confidence=expression.confidence,
                    extraction_run_id=run.id,
                    extractor_version=extractor_version,
                    fingerprint=fingerprint,
                    created_at=now,
                    updated_at=now,
                )
            )
        await self.session.flush()
