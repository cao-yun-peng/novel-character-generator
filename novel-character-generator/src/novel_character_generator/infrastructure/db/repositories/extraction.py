from datetime import UTC, datetime
from decimal import Decimal
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
    ChapterORM,
    CharacterORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    MentionSpanORM,
    NormalizationMapORM,
    PipelineRunORM,
    SceneORM,
    SourceDocumentORM,
    SourceDocumentVersionORM,
    StoryEventORM,
    TextChunkORM,
    TimelineORM,
)


class ExtractionRepository:
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

    async def persist_temporal_hypotheses(
        self,
        *,
        run: PipelineRunORM,
        chunk: TextChunkORM,
        document: SourceDocumentVersionORM,
        canonical_timeline: TimelineORM,
        result: ChunkExtractionResult,
    ) -> list[SceneORM]:
        timelines: dict[str, TimelineORM] = {canonical_timeline.name: canonical_timeline}
        for timeline_hypothesis in result.timeline_hypotheses:
            grounding = validate_evidence(
                chunk.content,
                timeline_hypothesis.evidence_quote,
                timeline_hypothesis.start,
                timeline_hypothesis.end,
            )
            if grounding == "ungrounded":
                continue
            if timeline_hypothesis.canonicality == "canonical":
                timelines[timeline_hypothesis.name] = canonical_timeline
                continue
            timeline = await self.session.scalar(
                select(TimelineORM).where(
                    TimelineORM.novel_id == run.novel_id,
                    TimelineORM.name == timeline_hypothesis.name,
                )
            )
            if timeline is None:
                timeline = TimelineORM(
                    id=uuid4(),
                    novel_id=run.novel_id,
                    name=timeline_hypothesis.name,
                    parent_timeline_id=canonical_timeline.id,
                    branch_event_id=None,
                    canonicality=timeline_hypothesis.canonicality,
                )
                self.session.add(timeline)
                await self.session.flush()
            timelines[timeline_hypothesis.name] = timeline

        chapter_ordinal = 0
        if chunk.chapter_id is not None:
            chapter = await self.session.get(ChapterORM, chunk.chapter_id)
            if chapter is not None:
                chapter_ordinal = chapter.ordinal
        now = datetime.now(UTC)
        scenes: list[SceneORM] = []
        for index, scene_hypothesis in enumerate(result.scene_hypotheses):
            quote = chunk.content[scene_hypothesis.start : scene_hypothesis.end]
            if (
                validate_evidence(
                    chunk.content,
                    quote,
                    scene_hypothesis.start,
                    scene_hypothesis.end,
                )
                == "ungrounded"
            ):
                continue
            timeline = canonical_timeline
            if scene_hypothesis.timeline_name:
                timeline = timelines.get(scene_hypothesis.timeline_name)
                if timeline is None:
                    timeline = await self.session.scalar(
                        select(TimelineORM).where(
                            TimelineORM.novel_id == run.novel_id,
                            TimelineORM.name == scene_hypothesis.timeline_name,
                        )
                    )
                if timeline is None:
                    timeline = TimelineORM(
                        id=uuid4(),
                        novel_id=run.novel_id,
                        name=scene_hypothesis.timeline_name,
                        parent_timeline_id=canonical_timeline.id,
                        branch_event_id=None,
                        canonicality="hypothetical",
                    )
                    self.session.add(timeline)
                    await self.session.flush()
                timelines[scene_hypothesis.timeline_name] = timeline
            scene = await self.session.scalar(
                select(SceneORM).where(
                    SceneORM.source_chunk_id == chunk.id,
                    SceneORM.char_start == scene_hypothesis.start,
                    SceneORM.char_end == scene_hypothesis.end,
                )
            )
            if scene is not None:
                scenes.append(scene)
                continue
            if index >= 1_000:
                raise ValueError("too_many_scenes_in_chunk")
            narrative_order = chunk.ordinal * 1_000 + index
            event = None
            if scene_hypothesis.label:
                event = StoryEventORM(
                    id=uuid4(),
                    timeline_id=timeline.id,
                    name=scene_hypothesis.label,
                    story_order=Decimal(narrative_order),
                    starts_at=None,
                    ends_at=None,
                )
                self.session.add(event)
                await self.session.flush()
            scene = SceneORM(
                id=uuid4(),
                novel_id=run.novel_id,
                timeline_id=timeline.id,
                event_id=event.id if event else None,
                chapter_ordinal=chapter_ordinal,
                narrative_order=narrative_order,
                point_of_view_character_id=None,
                label=scene_hypothesis.label,
                source_document_version_id=document.id,
                source_chunk_id=chunk.id,
                char_start=scene_hypothesis.start,
                char_end=scene_hypothesis.end,
                presentation_mode=scene_hypothesis.presentation_mode,
                reality_status=scene_hypothesis.reality_status,
                confidence=scene_hypothesis.confidence,
                binding_status="hypothesis",
                binding_revision=1,
                created_by_run_id=run.id,
                created_at=now,
                updated_at=now,
            )
            self.session.add(scene)
            scenes.append(scene)
        await self.session.flush()
        return scenes

    @staticmethod
    def scene_for_span(scenes: list[SceneORM], start: int, end: int) -> SceneORM | None:
        containing = [
            scene
            for scene in scenes
            if scene.char_start is not None
            and scene.char_end is not None
            and scene.char_start <= start
            and end <= scene.char_end
        ]
        if not containing:
            return None
        return min(containing, key=lambda scene: (scene.char_end or 0) - (scene.char_start or 0))

    async def persist_result(
        self,
        *,
        run: PipelineRunORM,
        chunk: TextChunkORM,
        document: SourceDocumentVersionORM,
        normalization_map: NormalizationMapORM,
        timeline: TimelineORM,
        result: ChunkExtractionResult,
        extractor_version: str,
    ) -> None:
        now = datetime.now(UTC)
        scenes = await self.persist_temporal_hypotheses(
            run=run,
            chunk=chunk,
            document=document,
            canonical_timeline=timeline,
            result=result,
        )
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
        for relation in result.relations:
            characters[relation.source_character_name] = await self.get_or_create_character(
                run.novel_id, relation.source_character_name
            )
            characters[relation.target_character_name] = await self.get_or_create_character(
                run.novel_id, relation.target_character_name
            )

        mentions_by_span: dict[tuple[int, int], MentionSpanORM] = {}
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
            mentions_by_span[(mention.start, mention.end)] = span
        await self.session.flush()

        for alias in result.alias_hypotheses:
            alias_span = mentions_by_span.get((alias.mention_start, alias.mention_end))
            if alias_span is None:
                grounding = validate_evidence(
                    chunk.content, alias.alias_text, alias.mention_start, alias.mention_end
                )
                owner = characters.get(alias.canonical_name or "")
                alias_span = await self.session.scalar(
                    select(MentionSpanORM).where(
                        MentionSpanORM.source_chunk_id == chunk.id,
                        MentionSpanORM.char_start == alias.mention_start,
                        MentionSpanORM.char_end == alias.mention_end,
                        MentionSpanORM.mention_text == alias.alias_text,
                        MentionSpanORM.mention_kind == alias.alias_kind,
                    )
                )
                if alias_span is None:
                    alias_span = MentionSpanORM(
                        id=uuid4(),
                        source_document_version=str(document.version),
                        source_document_version_id=document.id,
                        source_chunk_id=chunk.id,
                        char_start=alias.mention_start,
                        char_end=alias.mention_end,
                        mention_text=alias.alias_text,
                        mention_kind=alias.alias_kind,
                        candidate_character_ids=[str(owner.id)] if owner else [],
                        resolved_character_id=None,
                        grounding_status=grounding,
                        normalization_map_version=normalization_map.algorithm_version,
                        created_at=now,
                        updated_at=now,
                    )
                    self.session.add(alias_span)
                    await self.session.flush()
            owner = characters.get(alias.canonical_name or "")
            alias_scene = self.scene_for_span(
                scenes, alias.mention_start, alias.mention_end
            )
            existing_alias_id = await self.session.scalar(
                select(AliasAssertionORM.id).where(
                    AliasAssertionORM.mention_span_id == alias_span.id,
                    AliasAssertionORM.alias_text == alias.alias_text,
                    AliasAssertionORM.proposed_character_id == (owner.id if owner else None),
                )
            )
            if existing_alias_id is None:
                self.session.add(AliasAssertionORM(
                    id=uuid4(),
                    alias_text=alias.alias_text,
                    alias_kind=alias.alias_kind,
                    normalized_alias=alias.alias_text.casefold(),
                    mention_span_id=alias_span.id,
                    proposed_character_id=owner.id if owner else None,
                    speaker_id=None,
                    scene_id=alias_scene.id if alias_scene else None,
                    timeline_id=alias_scene.timeline_id if alias_scene else timeline.id,
                    supporting_evidence_ids=[str(alias_span.id)],
                    opposing_evidence_ids=[],
                    status="proposed",
                    created_at=now,
                    updated_at=now,
                ))

        for observation in result.observations:
            grounding = validate_evidence(
                chunk.content, observation.evidence_quote, observation.start, observation.end
            )
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
            observation_scene = self.scene_for_span(
                scenes, observation.start, observation.end
            )
            observation_timeline_id = (
                observation_scene.timeline_id if observation_scene else timeline.id
            )
            self.session.add(
                FeatureObservationORM(
                    id=uuid4(),
                    character_id=character.id,
                    field_path=observation.field_path,
                    value=observation.value,
                    source_kind="text",
                    source_document_version_id=document.id,
                    source_chunk_id=chunk.id,
                    mention_span_id=None,
                    evidence_quote=observation.evidence_quote,
                    char_start=observation.start,
                    char_end=observation.end,
                    chapter_ordinal=None,
                    scene_id=observation_scene.id if observation_scene else None,
                    event_id=observation_scene.event_id if observation_scene else None,
                    temporal_scope={
                        "timeline_id": str(observation_timeline_id),
                        "scope_type": "scene" if observation_scene else "unknown",
                        "presentation_mode": (
                            observation_scene.presentation_mode
                            if observation_scene
                            else "direct"
                        ),
                        "reality_status": (
                            observation_scene.reality_status
                            if observation_scene
                            else "canonical"
                        ),
                    },
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
                    record_status="active",
                    recorded_at=now,
                    invalidated_at=None,
                    invalidated_by_run_id=None,
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
                source_version=f"{document.source_document_id}:{document.version}",
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
            expression_scene = self.scene_for_span(
                scenes, expression.start, expression.end
            )
            expression_timeline_id = (
                expression_scene.timeline_id if expression_scene else timeline.id
            )
            self.session.add(
                ExpressionObservationORM(
                    id=uuid4(),
                    character_id=character.id,
                    source_document_version_id=document.id,
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
                    scene_id=expression_scene.id if expression_scene else None,
                    temporal_scope={
                        "timeline_id": str(expression_timeline_id),
                        "scope_type": "instant" if expression_scene else "unknown",
                        "presentation_mode": (
                            expression_scene.presentation_mode
                            if expression_scene
                            else "direct"
                        ),
                        "reality_status": (
                            expression_scene.reality_status
                            if expression_scene
                            else "canonical"
                        ),
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
