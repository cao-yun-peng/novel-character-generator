from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.extraction import (
    ChunkExtractionResult,
    ObservationDraft,
)
from novel_character_generator.domain.policies.grounding import (
    GroundingStatus,
    observation_fingerprint,
    repair_evidence_span,
    validate_evidence,
)
from novel_character_generator.domain.policies.relationships import (
    canonical_relation_type,
    kinship_placeholder_names,
    relation_type_for_family_field,
)
from novel_character_generator.domain.policies.visual_fields import (
    normalize_life_phase,
    normalize_observation_fields,
)
from novel_character_generator.infrastructure.db.orm import (
    AliasAssertionORM,
    ChapterORM,
    CharacterAppearanceStateORM,
    CharacterORM,
    CharacterRelationORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    FeatureSuggestionORM,
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

CANONICAL_TIMELINE_ALIASES = frozenset(
    {
        "main",
        "main_timeline",
        "canonical",
        "canonical_timeline",
        "主线",
        "主时间线",
        "主线时间线",
    }
)


def is_canonical_timeline_name(name: str | None) -> bool:
    if not name:
        return False
    token = name.strip().casefold().replace("-", "_").replace(" ", "_")
    return token in CANONICAL_TIMELINE_ALIASES


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

    async def supersede_prior_extractor_observations(
        self,
        *,
        run: PipelineRunORM,
        document: SourceDocumentVersionORM,
        extractor_version: str,
    ) -> None:
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

    async def activate_run_observations(self, *, run: PipelineRunORM) -> None:
        """Publish observations only after every chunk in the run has succeeded."""
        now = datetime.now(UTC)
        await self.session.execute(
            update(FeatureObservationORM)
            .where(
                FeatureObservationORM.extraction_run_id == run.id,
                FeatureObservationORM.record_status == "pending",
            )
            .values(record_status="active", recorded_at=now, updated_at=now)
        )
        await self.session.execute(
            update(CharacterRelationORM)
            .where(
                CharacterRelationORM.extraction_run_id == run.id,
                CharacterRelationORM.record_status == "pending",
            )
            .values(record_status="active", updated_at=now)
        )

    async def kinship_name_aliases(
        self,
        *,
        novel_id: UUID,
        observations: list[tuple[ObservationDraft, GroundingStatus]],
    ) -> dict[str, str]:
        aliases: dict[str, str] = {}

        def add(source_name: str, field_path: str, value: object) -> None:
            relation_type = relation_type_for_family_field(field_path)
            if relation_type is None or not isinstance(value, str) or not value.strip():
                return
            target_name = value.strip()
            for placeholder in kinship_placeholder_names(source_name, relation_type):
                aliases[placeholder] = target_name

        rows = await self.session.execute(
            select(
                CharacterORM.canonical_name,
                FeatureObservationORM.field_path,
                FeatureObservationORM.value,
            )
            .join(CharacterORM, CharacterORM.id == FeatureObservationORM.character_id)
            .where(
                CharacterORM.novel_id == novel_id,
                FeatureObservationORM.field_path.like("family.%"),
                FeatureObservationORM.record_status.in_(("active", "pending")),
            )
        )
        for source_name, field_path, value in rows:
            add(source_name, field_path, value)
        for observation, _ in observations:
            add(observation.character_name, observation.field_path, observation.value)
        return aliases

    async def reconcile_kinship_placeholders(
        self, *, novel_id: UUID, aliases: dict[str, str]
    ) -> None:
        """Merge empty kinship placeholders without deleting their audit identity."""
        now = datetime.now(UTC)
        for placeholder_name, target_name in sorted(aliases.items()):
            if placeholder_name == target_name:
                continue
            placeholder = await self.session.scalar(
                select(CharacterORM).where(
                    CharacterORM.novel_id == novel_id,
                    CharacterORM.canonical_name == placeholder_name,
                    CharacterORM.merged_into_character_id.is_(None),
                )
            )
            target = await self.session.scalar(
                select(CharacterORM).where(
                    CharacterORM.novel_id == novel_id,
                    CharacterORM.canonical_name == target_name,
                )
            )
            if placeholder is None or target is None or placeholder.id == target.id:
                continue
            substantive = False
            for model in (
                FeatureObservationORM,
                ExpressionObservationORM,
                CharacterAppearanceStateORM,
                FeatureSuggestionORM,
            ):
                owned_id = await self.session.scalar(
                    select(model.id).where(model.character_id == placeholder.id).limit(1)
                )
                if owned_id is not None:
                    substantive = True
                    break
            if substantive:
                continue
            mentions = list(
                await self.session.scalars(
                    select(MentionSpanORM).where(
                        MentionSpanORM.resolved_character_id == placeholder.id
                    )
                )
            )
            for mention in mentions:
                mention.resolved_character_id = target.id
                mention.candidate_character_ids = list(
                    dict.fromkeys(
                        str(target.id)
                        if candidate.replace("-", "").casefold()
                        == str(placeholder.id).replace("-", "").casefold()
                        else candidate
                        for candidate in mention.candidate_character_ids
                    )
                )
                mention.updated_at = now
            await self.session.execute(
                update(AliasAssertionORM)
                .where(AliasAssertionORM.proposed_character_id == placeholder.id)
                .values(proposed_character_id=target.id, updated_at=now)
            )
            await self.session.execute(
                update(AliasAssertionORM)
                .where(AliasAssertionORM.speaker_id == placeholder.id)
                .values(speaker_id=target.id, updated_at=now)
            )
            await self.session.execute(
                update(CharacterRelationORM)
                .where(CharacterRelationORM.source_character_id == placeholder.id)
                .values(source_character_id=target.id, updated_at=now)
            )
            await self.session.execute(
                update(CharacterRelationORM)
                .where(CharacterRelationORM.target_character_id == placeholder.id)
                .values(target_character_id=target.id, updated_at=now)
            )
            placeholder.status = "merged"
            placeholder.merged_into_character_id = target.id
            placeholder.revision += 1
            placeholder.updated_at = now

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
            if (
                timeline_hypothesis.canonicality == "canonical"
                or is_canonical_timeline_name(timeline_hypothesis.name)
            ):
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
            if index >= 1_000:
                raise ValueError("too_many_scenes_in_chunk")
            narrative_order = chunk.ordinal * 1_000 + index
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
                if is_canonical_timeline_name(scene_hypothesis.timeline_name):
                    timeline = canonical_timeline
                    timelines[scene_hypothesis.timeline_name] = canonical_timeline
                else:
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
                    SceneORM.novel_id == run.novel_id,
                    SceneORM.narrative_order == narrative_order,
                )
            )
            if scene is not None:
                scene.chapter_ordinal = chapter_ordinal
                scene.label = scene_hypothesis.label
                scene.source_document_version_id = document.id
                scene.source_chunk_id = chunk.id
                scene.char_start = scene_hypothesis.start
                scene.char_end = scene_hypothesis.end
                scene.confidence = scene_hypothesis.confidence
                scene.updated_at = now
                if scene.binding_status != "corrected":
                    event = (
                        await self.session.get(StoryEventORM, scene.event_id)
                        if scene.event_id is not None
                        else None
                    )
                    if scene_hypothesis.label:
                        if event is None:
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
                        else:
                            event.timeline_id = timeline.id
                            event.name = scene_hypothesis.label
                            event.story_order = Decimal(narrative_order)
                        scene.event_id = event.id
                    else:
                        scene.event_id = None
                    scene.timeline_id = timeline.id
                    scene.presentation_mode = scene_hypothesis.presentation_mode
                    scene.reality_status = scene_hypothesis.reality_status
                scenes.append(scene)
                continue
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
        chapter_ordinal: int | None = None
        if chunk.chapter_id is not None:
            chapter = await self.session.get(ChapterORM, chunk.chapter_id)
            chapter_ordinal = chapter.ordinal if chapter is not None else None
        scenes = await self.persist_temporal_hypotheses(
            run=run,
            chunk=chunk,
            document=document,
            canonical_timeline=timeline,
            result=result,
        )
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
        name_aliases = await self.kinship_name_aliases(
            novel_id=run.novel_id, observations=prepared_observations
        )
        requested_names = {
            *(mention.canonical_name for mention in result.mentions if mention.canonical_name),
            *(observation.character_name for observation, _ in prepared_observations),
            *(expression.character_name for expression in result.expression_observations),
            *(relation.source_character_name for relation in result.relations),
            *(relation.target_character_name for relation in result.relations),
        }
        for observation, _ in prepared_observations:
            if (
                relation_type_for_family_field(observation.field_path) is not None
                and isinstance(observation.value, str)
                and observation.value.strip()
            ):
                requested_names.add(observation.value.strip())
        canonical_names = {
            name: name_aliases.get(name.strip(), name.strip()) for name in requested_names
        }
        canonical_characters: dict[str, CharacterORM] = {}
        for canonical_name in sorted(set(canonical_names.values())):
            canonical_characters[canonical_name] = await self.get_or_create_character(
                run.novel_id, canonical_name
            )
        characters = {
            name: canonical_characters[canonical_name]
            for name, canonical_name in canonical_names.items()
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
                if (scope or {}).get("life_phase_key")
                in {"past_life", "reincarnated_childhood"}
            )
        phase_adjusted_observations: list[tuple[ObservationDraft, GroundingStatus]] = []
        for observation, grounding in prepared_observations:
            character = characters.get(observation.character_name)
            updates: dict[str, object] = {}
            if (
                observation.field_path
                in {"identity.experienced_age", "identity.mental_age_stage"}
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
            phase_adjusted_observations.append(
                (observation.model_copy(update=updates) if updates else observation, grounding)
            )
        prepared_observations = phase_adjusted_observations

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

        for observation, grounding in prepared_observations:
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
            temporal_scope = {
                "timeline_id": str(observation_timeline_id),
                "scope_type": "scene" if observation_scene else "unknown",
                "start_chapter_ordinal": (
                    observation_scene.chapter_ordinal
                    if observation_scene
                    else chapter_ordinal
                ),
                "presentation_mode": (
                    observation_scene.presentation_mode if observation_scene else "direct"
                ),
                "reality_status": (
                    observation_scene.reality_status if observation_scene else "canonical"
                ),
            }
            if observation.life_phase_key is not None:
                temporal_scope["life_phase_key"] = observation.life_phase_key
            if observation.life_phase_label is not None:
                temporal_scope["life_phase_label"] = observation.life_phase_label
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
                    chapter_ordinal=chapter_ordinal,
                    scene_id=observation_scene.id if observation_scene else None,
                    event_id=observation_scene.event_id if observation_scene else None,
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

        prepared_relations: list[
            tuple[str, str, str, str, int, int, float, GroundingStatus]
        ] = []
        for relation in result.relations:
            start, end, grounding = repair_evidence_span(
                chunk.content,
                relation.evidence_quote,
                relation.start,
                relation.end,
            )
            prepared_relations.append(
                (
                    relation.source_character_name,
                    relation.target_character_name,
                    canonical_relation_type(relation.relation_type),
                    relation.evidence_quote,
                    start,
                    end,
                    relation.confidence,
                    grounding,
                )
            )
        for observation, grounding in prepared_observations:
            relation_type = relation_type_for_family_field(observation.field_path)
            if (
                relation_type is None
                or not isinstance(observation.value, str)
                or not observation.value.strip()
            ):
                continue
            prepared_relations.append(
                (
                    observation.character_name,
                    observation.value.strip(),
                    relation_type,
                    observation.evidence_quote,
                    observation.start,
                    observation.end,
                    observation.confidence,
                    grounding,
                )
            )

        for (
            source_name,
            target_name,
            relation_type,
            evidence_quote,
            start,
            end,
            confidence,
            grounding,
        ) in prepared_relations:
            if grounding == "ungrounded":
                continue
            source_character = characters[source_name]
            target_character = characters[target_name]
            fingerprint = observation_fingerprint(
                source_version=f"{document.source_document_id}:{document.version}",
                start=chunk.normalized_char_start + start,
                end=chunk.normalized_char_start + end,
                field_path=f"relation.{relation_type}.{source_character.id}",
                value=str(target_character.id),
                extractor_version=extractor_version,
            )
            exists = await self.session.scalar(
                select(CharacterRelationORM.id).where(
                    CharacterRelationORM.fingerprint == fingerprint
                )
            )
            if exists is not None:
                continue
            relation_scene = self.scene_for_span(scenes, start, end)
            self.session.add(
                CharacterRelationORM(
                    id=uuid4(),
                    novel_id=run.novel_id,
                    source_character_id=source_character.id,
                    target_character_id=target_character.id,
                    relation_type=relation_type,
                    source_document_version_id=document.id,
                    source_chunk_id=chunk.id,
                    scene_id=relation_scene.id if relation_scene else None,
                    evidence_quote=evidence_quote,
                    char_start=start,
                    char_end=end,
                    grounding_status=grounding,
                    confidence=confidence,
                    extraction_run_id=run.id,
                    extractor_version=extractor_version,
                    fingerprint=fingerprint,
                    record_status="pending",
                    created_at=now,
                    updated_at=now,
                )
            )
        await self.reconcile_kinship_placeholders(
            novel_id=run.novel_id, aliases=name_aliases
        )
        await self.session.flush()
