from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.infrastructure.db.orm import (
    AliasAssertionORM,
    DecisionRecordORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    NovelORM,
    SceneORM,
    StoryEventORM,
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
