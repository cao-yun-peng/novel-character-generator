from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.infrastructure.db.orm import (
    AliasAssertionORM,
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterLifePhaseORM,
    CharacterORM,
    CharacterRenderProfileORM,
    DecisionRecordORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    NovelORM,
    ObservationScopeBindingORM,
    PipelineRunORM,
    SceneORM,
    StoryEventORM,
    TemporalSignalORM,
    TimelineORM,
)


class TemporalBindingConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class TemporalBindingUpdate:
    timeline_id: UUID
    event_id: UUID | None
    presentation_mode: Literal[
        "direct", "flashback", "flashforward", "dream", "illusion", "rumor", "hypothetical"
    ]
    reality_status: Literal["canonical", "subjective", "alleged", "counterfactual"]


@dataclass(frozen=True)
class LifePhaseUpdate:
    label: str
    start_chapter_ordinal: int | None
    end_chapter_ordinal: int | None
    status: Literal["active", "rejected"]
    reason: str


class StoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def novel_exists(self, novel_id: UUID) -> bool:
        return await self.session.get(NovelORM, novel_id) is not None

    async def timelines(self, novel_id: UUID) -> list[TimelineORM]:
        return list(
            await self.session.scalars(
                select(TimelineORM)
                .where(TimelineORM.novel_id == novel_id)
                .order_by(TimelineORM.canonicality, TimelineORM.name, TimelineORM.id)
            )
        )

    async def events(self, novel_id: UUID) -> list[StoryEventORM]:
        return list(
            await self.session.scalars(
                select(StoryEventORM)
                .join(TimelineORM, StoryEventORM.timeline_id == TimelineORM.id)
                .where(TimelineORM.novel_id == novel_id)
                .order_by(StoryEventORM.story_order, StoryEventORM.id)
            )
        )

    async def scenes(self, novel_id: UUID) -> list[SceneORM]:
        return list(
            await self.session.scalars(
                select(SceneORM)
                .where(SceneORM.novel_id == novel_id)
                .order_by(SceneORM.narrative_order, SceneORM.id)
            )
        )

    async def life_phases(self, character_id: UUID) -> list[CharacterLifePhaseORM] | None:
        if await self.session.get(CharacterORM, character_id) is None:
            return None
        return list(
            await self.session.scalars(
                select(CharacterLifePhaseORM)
                .where(
                    CharacterLifePhaseORM.character_id == character_id,
                    CharacterLifePhaseORM.record_status == "active",
                )
                .order_by(
                    CharacterLifePhaseORM.timeline_id,
                    CharacterLifePhaseORM.phase_order,
                    CharacterLifePhaseORM.id,
                )
            )
        )

    async def temporal_review(
        self, novel_id: UUID
    ) -> tuple[list[TemporalSignalORM], list[ObservationScopeBindingORM]] | None:
        if await self.session.get(NovelORM, novel_id) is None:
            return None
        signals = list(
            await self.session.scalars(
                select(TemporalSignalORM)
                .join(PipelineRunORM, TemporalSignalORM.run_id == PipelineRunORM.id)
                .where(
                    PipelineRunORM.novel_id == novel_id,
                    TemporalSignalORM.resolution_status == "unresolved",
                )
                .order_by(
                    TemporalSignalORM.source_chunk_id,
                    TemporalSignalORM.char_start,
                    TemporalSignalORM.id,
                )
            )
        )
        bindings = list(
            await self.session.scalars(
                select(ObservationScopeBindingORM)
                .join(
                    FeatureObservationORM,
                    ObservationScopeBindingORM.observation_id == FeatureObservationORM.id,
                )
                .join(CharacterORM, FeatureObservationORM.character_id == CharacterORM.id)
                .where(
                    CharacterORM.novel_id == novel_id,
                    ObservationScopeBindingORM.status == "needs_review",
                    ObservationScopeBindingORM.record_status == "active",
                )
                .order_by(
                    ObservationScopeBindingORM.created_at,
                    ObservationScopeBindingORM.id,
                )
            )
        )
        return signals, bindings

    async def resolve_life_phase(
        self,
        character_id: UUID,
        phase_id: UUID,
        *,
        update_request: LifePhaseUpdate,
        expected_revision: int,
        actor_id: str,
    ) -> CharacterLifePhaseORM | None:
        phase = await self.session.get(CharacterLifePhaseORM, phase_id)
        if phase is None or phase.character_id != character_id:
            return None
        if phase.record_status != "active":
            raise ValueError("life_phase_stale")
        if (
            update_request.start_chapter_ordinal is not None
            and update_request.end_chapter_ordinal is not None
            and update_request.end_chapter_ordinal < update_request.start_chapter_ordinal
        ):
            raise ValueError("life_phase_invalid_chapter_range")
        now = datetime.now(UTC)
        previous = {
            "label": phase.label,
            "start_chapter_ordinal": phase.start_chapter_ordinal,
            "end_chapter_ordinal": phase.end_chapter_ordinal,
            "status": phase.status,
            "revision": phase.revision,
        }
        updated_id = await self.session.scalar(
            update(CharacterLifePhaseORM)
            .where(
                CharacterLifePhaseORM.id == phase.id,
                CharacterLifePhaseORM.revision == expected_revision,
                CharacterLifePhaseORM.record_status == "active",
            )
            .values(
                label=update_request.label,
                start_chapter_ordinal=update_request.start_chapter_ordinal,
                end_chapter_ordinal=update_request.end_chapter_ordinal,
                status=update_request.status,
                resolver_version="manual-phase-resolution-v1",
                revision=expected_revision + 1,
                updated_at=now,
            )
            .returning(CharacterLifePhaseORM.id)
        )
        if updated_id is None:
            await self.session.rollback()
            raise TemporalBindingConflict("life_phase_revision_conflict")

        bindings = list(
            await self.session.scalars(
                select(ObservationScopeBindingORM).where(
                    ObservationScopeBindingORM.phase_id == phase.id,
                    ObservationScopeBindingORM.record_status == "active",
                )
            )
        )
        for binding in bindings:
            scope = dict(binding.temporal_scope)
            scope.update(
                {
                    "life_phase_label": update_request.label,
                    "start_chapter_ordinal": update_request.start_chapter_ordinal,
                    "scope_resolution_status": (
                        "final" if update_request.status == "active" else "needs_review"
                    ),
                    "phase_resolver_version": "manual-phase-resolution-v1",
                }
            )
            if update_request.end_chapter_ordinal is None:
                scope.pop("end_chapter_ordinal", None)
            else:
                scope["end_chapter_ordinal"] = update_request.end_chapter_ordinal
            binding.temporal_scope = scope
            binding.status = "final" if update_request.status == "active" else "needs_review"
            binding.resolver_version = "manual-phase-resolution-v1"
            binding.revision += 1
            binding.updated_at = now
            observation = await self.session.get(FeatureObservationORM, binding.observation_id)
            if observation is not None:
                observation.temporal_scope = scope
                observation.record_status = (
                    "active" if update_request.status == "active" else "pending"
                )
                observation.recorded_at = now if update_request.status == "active" else None
                observation.updated_at = now

        await self.session.execute(
            update(CharacterAppearanceStateORM)
            .where(
                CharacterAppearanceStateORM.character_id == character_id,
                CharacterAppearanceStateORM.record_status == "active",
            )
            .values(record_status="invalidated", updated_at=now)
        )
        await self.session.execute(
            update(CharacterRenderProfileORM)
            .where(
                CharacterRenderProfileORM.character_id == character_id,
                CharacterRenderProfileORM.record_status == "active",
            )
            .values(record_status="invalidated", updated_at=now)
        )
        await self.session.execute(
            update(CharacterConflictORM)
            .where(
                CharacterConflictORM.character_id == character_id,
                CharacterConflictORM.status == "pending",
            )
            .values(status="superseded", updated_at=now)
        )
        self.session.add(
            DecisionRecordORM(
                id=uuid4(),
                pipeline_run_id=phase.run_id,
                agent_run_id=None,
                decision_kind="life_phase_resolution",
                subject_type="character_life_phase",
                subject_id=phase.id,
                decision={
                    "actor_id": actor_id,
                    "reason": update_request.reason,
                    "previous": previous,
                    "updated": {
                        "label": update_request.label,
                        "start_chapter_ordinal": update_request.start_chapter_ordinal,
                        "end_chapter_ordinal": update_request.end_chapter_ordinal,
                        "status": update_request.status,
                        "revision": expected_revision + 1,
                    },
                    "reaggregation_required": True,
                },
                evidence_ids=phase.evidence_signal_ids,
                source_kind="manual",
                created_at=now,
                updated_at=now,
            )
        )
        await self.session.commit()
        return await self.session.get_one(CharacterLifePhaseORM, phase.id)

    async def update_temporal_binding(
        self,
        scene_id: UUID,
        *,
        binding: TemporalBindingUpdate,
        expected_revision: int,
        actor_id: str,
    ) -> SceneORM | None:
        scene = await self.session.get(SceneORM, scene_id)
        if scene is None:
            return None
        timeline = await self.session.get(TimelineORM, binding.timeline_id)
        if timeline is None or timeline.novel_id != scene.novel_id:
            raise ValueError("scene_timeline_novel_mismatch")
        if binding.event_id is not None:
            event = await self.session.get(StoryEventORM, binding.event_id)
            if event is None or event.timeline_id != binding.timeline_id:
                raise ValueError("scene_event_timeline_mismatch")
        if scene.created_by_run_id is None:
            raise ValueError("scene_source_run_required_for_audit")
        now = datetime.now(UTC)
        previous = {
            "timeline_id": str(scene.timeline_id),
            "event_id": str(scene.event_id) if scene.event_id else None,
            "presentation_mode": scene.presentation_mode,
            "reality_status": scene.reality_status,
            "binding_revision": scene.binding_revision,
        }
        updated_id = await self.session.scalar(
            update(SceneORM)
            .where(
                SceneORM.id == scene.id,
                SceneORM.binding_revision == expected_revision,
            )
            .values(
                timeline_id=binding.timeline_id,
                event_id=binding.event_id,
                presentation_mode=binding.presentation_mode,
                reality_status=binding.reality_status,
                binding_status="corrected",
                binding_revision=expected_revision + 1,
                updated_at=now,
            )
            .returning(SceneORM.id)
        )
        if updated_id is None:
            await self.session.rollback()
            raise TemporalBindingConflict("scene_binding_revision_conflict")
        observations = list(
            await self.session.scalars(
                select(FeatureObservationORM).where(
                    FeatureObservationORM.scene_id == scene.id,
                    FeatureObservationORM.record_status == "active",
                )
            )
        )
        for observation in observations:
            scope = dict(observation.temporal_scope or {})
            scope.update(
                {
                    "timeline_id": str(binding.timeline_id),
                    "presentation_mode": binding.presentation_mode,
                    "reality_status": binding.reality_status,
                }
            )
            observation.temporal_scope = scope
            observation.event_id = binding.event_id
            observation.updated_at = now
        expressions = list(
            await self.session.scalars(
                select(ExpressionObservationORM).where(
                    ExpressionObservationORM.scene_id == scene.id
                )
            )
        )
        for expression in expressions:
            scope = dict(expression.temporal_scope)
            scope.update(
                {
                    "timeline_id": str(binding.timeline_id),
                    "presentation_mode": binding.presentation_mode,
                    "reality_status": binding.reality_status,
                }
            )
            expression.temporal_scope = scope
            expression.updated_at = now
        aliases = list(
            await self.session.scalars(
                select(AliasAssertionORM).where(AliasAssertionORM.scene_id == scene.id)
            )
        )
        for alias in aliases:
            alias.timeline_id = binding.timeline_id
            alias.updated_at = now
        self.session.add(
            DecisionRecordORM(
                id=uuid4(),
                pipeline_run_id=scene.created_by_run_id,
                agent_run_id=None,
                decision_kind="temporal_binding",
                subject_type="scene",
                subject_id=scene.id,
                decision={
                    "actor_id": actor_id,
                    "previous": previous,
                    "updated": {
                        "timeline_id": str(binding.timeline_id),
                        "event_id": str(binding.event_id) if binding.event_id else None,
                        "presentation_mode": binding.presentation_mode,
                        "reality_status": binding.reality_status,
                        "binding_revision": expected_revision + 1,
                    },
                },
                evidence_ids=[str(scene.source_chunk_id)] if scene.source_chunk_id else [],
                source_kind="manual",
                created_at=now,
                updated_at=now,
            )
        )
        await self.session.commit()
        return await self.session.get_one(SceneORM, scene.id)
