from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.infrastructure.db.orm import (
    AliasAssertionORM,
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterEntityOperationORM,
    CharacterImageSetORM,
    CharacterORM,
    CharacterRenderProfileORM,
    DecisionRecordORM,
    EventParticipantORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    FeatureSuggestionORM,
    GeneratedImageORM,
    HumanApprovalORM,
    MentionSpanORM,
    SceneORM,
    TextChunkORM,
)


class EntityOperationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class MergeSource:
    character_id: UUID
    expected_revision: int


@dataclass(frozen=True)
class SplitAssignments:
    mention_span_ids: list[UUID] = field(default_factory=list)
    alias_assertion_ids: list[UUID] = field(default_factory=list)
    observation_ids: list[UUID] = field(default_factory=list)
    expression_ids: list[UUID] = field(default_factory=list)
    appearance_state_ids: list[UUID] = field(default_factory=list)
    suggestion_ids: list[UUID] = field(default_factory=list)
    event_participant_ids: list[UUID] = field(default_factory=list)
    scene_ids: list[UUID] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "mention_span_ids": [str(item) for item in self.mention_span_ids],
            "alias_assertion_ids": [str(item) for item in self.alias_assertion_ids],
            "observation_ids": [str(item) for item in self.observation_ids],
            "expression_ids": [str(item) for item in self.expression_ids],
            "appearance_state_ids": [str(item) for item in self.appearance_state_ids],
            "suggestion_ids": [str(item) for item in self.suggestion_ids],
            "event_participant_ids": [str(item) for item in self.event_participant_ids],
            "scene_ids": [str(item) for item in self.scene_ids],
        }

    def item_count(self) -> int:
        return sum(len(items) for items in self.as_dict().values())


@dataclass(frozen=True)
class SplitTarget:
    canonical_name: str
    reuse_source: bool
    assignments: SplitAssignments


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _replace_ids(values: list[str], sources: set[UUID], target: UUID) -> list[str]:
    result: list[str] = []
    for value in values:
        try:
            parsed = UUID(value)
        except ValueError:
            parsed = None
        replacement = str(target) if parsed in sources else value
        if replacement not in result:
            result.append(replacement)
    return result


class CharacterEntityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def merge(
        self,
        *,
        target_character_id: UUID,
        expected_target_revision: int,
        sources: list[MergeSource],
        reason: str,
        actor_id: str,
        idempotency_key: str,
    ) -> CharacterEntityOperationORM:
        source_revisions = {str(item.character_id): item.expected_revision for item in sources}
        action = {
            "operation_type": "merge",
            "target_character_id": str(target_character_id),
            "expected_target_revision": expected_target_revision,
            "source_revisions": source_revisions,
            "reason": reason,
        }
        request_hash = _hash(action)
        existing = await self._idempotent_operation(idempotency_key, request_hash)
        if existing is not None:
            return existing
        source_ids = [item.character_id for item in sources]
        if not source_ids or len(set(source_ids)) != len(source_ids):
            raise ValueError("merge_sources_invalid")
        if target_character_id in source_ids:
            raise ValueError("merge_target_cannot_be_source")
        target = await self.session.get(CharacterORM, target_character_id)
        if target is None:
            raise ValueError("merge_target_not_found")
        if target.status != "active" or target.merged_into_character_id is not None:
            raise EntityOperationConflict("merge_target_not_active")
        source_rows: list[CharacterORM] = []
        expected_by_id = {item.character_id: item.expected_revision for item in sources}
        for source_id in source_ids:
            source = await self.session.get(CharacterORM, source_id)
            if source is None:
                raise ValueError("merge_source_not_found")
            if source.novel_id != target.novel_id:
                raise ValueError("merge_cross_novel_forbidden")
            if source.status != "active" or source.merged_into_character_id is not None:
                raise EntityOperationConflict("merge_source_not_active")
            source_rows.append(source)
        now = datetime.now(UTC)
        await self._reserve_revision(target, expected_target_revision, now)
        for source in source_rows:
            await self._reserve_revision(source, expected_by_id[source.id], now)
        before_snapshot = await self._entity_snapshot([target_character_id, *source_ids])
        source_set = set(source_ids)

        mentions = list(
            await self.session.scalars(
                select(MentionSpanORM)
                .join(TextChunkORM, MentionSpanORM.source_chunk_id == TextChunkORM.id)
                .where(TextChunkORM.novel_id == target.novel_id)
            )
        )
        for mention in mentions:
            changed = False
            if mention.resolved_character_id in source_set:
                mention.resolved_character_id = target_character_id
                changed = True
            candidate_ids = _replace_ids(
                mention.candidate_character_ids, source_set, target_character_id
            )
            if candidate_ids != mention.candidate_character_ids:
                mention.candidate_character_ids = candidate_ids
                changed = True
            if changed:
                mention.updated_at = now

        aliases = list(
            await self.session.scalars(
                select(AliasAssertionORM).where(
                    or_(
                        AliasAssertionORM.proposed_character_id.in_(source_ids),
                        AliasAssertionORM.speaker_id.in_(source_ids),
                    )
                )
            )
        )
        for alias in aliases:
            if alias.proposed_character_id in source_set:
                alias.proposed_character_id = target_character_id
            if alias.speaker_id in source_set:
                alias.speaker_id = target_character_id
            alias.updated_at = now

        await self._bulk_rebind(FeatureObservationORM, source_ids, target_character_id, now)
        await self._bulk_rebind(FeatureSuggestionORM, source_ids, target_character_id, now)
        await self._bulk_rebind(CharacterAppearanceStateORM, source_ids, target_character_id, now)
        await self._merge_conflicts(source_ids, target_character_id, now)
        await self._merge_event_participants(source_ids, target_character_id, now)

        await self.session.execute(
            update(ExpressionObservationORM)
            .where(ExpressionObservationORM.character_id.in_(source_ids))
            .values(character_id=target_character_id, updated_at=now)
        )
        await self.session.execute(
            update(ExpressionObservationORM)
            .where(ExpressionObservationORM.target_character_id.in_(source_ids))
            .values(target_character_id=target_character_id, updated_at=now)
        )
        await self.session.execute(
            update(SceneORM)
            .where(SceneORM.point_of_view_character_id.in_(source_ids))
            .values(point_of_view_character_id=target_character_id, updated_at=now)
        )
        await self._move_render_profiles(source_ids, target_character_id, now)
        await self._move_image_sets(source_ids, target_character_id, now)
        await self.session.execute(
            update(GeneratedImageORM)
            .where(GeneratedImageORM.character_id.in_(source_ids))
            .values(character_id=target_character_id, updated_at=now)
        )
        await self.session.execute(
            update(CharacterORM)
            .where(CharacterORM.id.in_(source_ids))
            .values(
                status="merged",
                merged_into_character_id=target_character_id,
                updated_at=now,
            )
        )
        operation = CharacterEntityOperationORM(
            id=uuid4(),
            operation_type="merge",
            novel_id=target.novel_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            source_character_ids=[str(item) for item in source_ids],
            target_character_ids=[str(target_character_id)],
            action=action,
            before_snapshot=before_snapshot,
            status="completed",
            actor_id=actor_id,
            reason=reason,
            created_at=now,
            updated_at=now,
        )
        self.session.add(operation)
        self._add_manual_audit(
            operation=operation,
            subject_id=target_character_id,
            decision_kind="character_merge",
            actor_id=actor_id,
            now=now,
        )
        await self.session.commit()
        return await self.session.get_one(CharacterEntityOperationORM, operation.id)

    async def split(
        self,
        *,
        source_character_id: UUID,
        expected_revision: int,
        targets: list[SplitTarget],
        invalidate_render_assets: bool,
        reason: str,
        actor_id: str,
        idempotency_key: str,
    ) -> CharacterEntityOperationORM:
        action = {
            "operation_type": "split",
            "source_character_id": str(source_character_id),
            "expected_revision": expected_revision,
            "targets": [
                {
                    "canonical_name": item.canonical_name,
                    "reuse_source": item.reuse_source,
                    "assignments": item.assignments.as_dict(),
                }
                for item in targets
            ],
            "invalidate_render_assets": invalidate_render_assets,
            "reason": reason,
        }
        request_hash = _hash(action)
        existing = await self._idempotent_operation(idempotency_key, request_hash)
        if existing is not None:
            return existing
        if len(targets) < 2 or sum(item.reuse_source for item in targets) != 1:
            raise ValueError("split_targets_require_exactly_one_source_reuse")
        names = [item.canonical_name.strip() for item in targets]
        if any(not item for item in names) or len(set(names)) != len(names):
            raise ValueError("split_target_names_invalid")
        if any(not item.reuse_source and item.assignments.item_count() == 0 for item in targets):
            raise ValueError("split_new_target_assignments_required")
        self._validate_assignment_uniqueness(targets)
        source = await self.session.get(CharacterORM, source_character_id)
        if source is None:
            raise ValueError("split_source_not_found")
        if source.status != "active" or source.merged_into_character_id is not None:
            raise EntityOperationConflict("split_source_not_active")
        conflicting_name = await self.session.scalar(
            select(CharacterORM.id)
            .where(
                CharacterORM.novel_id == source.novel_id,
                CharacterORM.canonical_name.in_(names),
                CharacterORM.id != source.id,
            )
            .limit(1)
        )
        if conflicting_name is not None:
            raise EntityOperationConflict("split_target_name_conflict")
        protected_assets = await self.session.scalar(
            select(CharacterRenderProfileORM.id)
            .where(
                CharacterRenderProfileORM.character_id == source.id,
                CharacterRenderProfileORM.status.in_(("approved", "locked")),
            )
            .limit(1)
        )
        if protected_assets is None:
            protected_assets = await self.session.scalar(
                select(CharacterImageSetORM.id)
                .where(
                    CharacterImageSetORM.character_id == source.id,
                    CharacterImageSetORM.status.in_(("partially_approved", "approved")),
                )
                .limit(1)
            )
        if protected_assets is None:
            protected_assets = await self.session.scalar(
                select(GeneratedImageORM.id)
                .where(GeneratedImageORM.character_id == source.id)
                .limit(1)
            )
        if protected_assets is not None and not invalidate_render_assets:
            raise EntityOperationConflict("split_requires_render_asset_invalidation")
        now = datetime.now(UTC)
        before_snapshot = await self._entity_snapshot([source.id])
        await self._reserve_revision(source, expected_revision, now)
        reuse_target = next(item for item in targets if item.reuse_source)
        source.canonical_name = reuse_target.canonical_name.strip()
        source.updated_at = now
        target_ids_by_name: dict[str, UUID] = {reuse_target.canonical_name: source.id}
        for target in targets:
            if target.reuse_source:
                continue
            target_id = uuid4()
            target_ids_by_name[target.canonical_name] = target_id
            self.session.add(
                CharacterORM(
                    id=target_id,
                    novel_id=source.novel_id,
                    canonical_name=target.canonical_name.strip(),
                    status="active",
                    revision=1,
                    merged_into_character_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        await self.session.flush()
        for target in targets:
            target_id = target_ids_by_name[target.canonical_name]
            await self._apply_split_assignments(
                source_character_id=source.id,
                target_character_id=target_id,
                assignments=target.assignments,
                now=now,
            )
        moved_state_ids = {
            state_id
            for target in targets
            if not target.reuse_source
            for state_id in target.assignments.appearance_state_ids
        }
        profiles = list(
            await self.session.scalars(
                select(CharacterRenderProfileORM).where(
                    CharacterRenderProfileORM.character_id == source.id
                )
            )
        )
        for profile in profiles:
            profile.appearance_state_ids = [
                item for item in profile.appearance_state_ids if UUID(item) not in moved_state_ids
            ]
            if profile.default_appearance_state_id in moved_state_ids:
                profile.default_appearance_state_id = None
            profile.status = "needs_review"
            profile.approved_by = None
            profile.approved_at = None
            profile.revision += 1
            profile.updated_at = now
        if moved_state_ids:
            await self.session.execute(
                update(CharacterConflictORM)
                .where(
                    CharacterConflictORM.character_id == source.id,
                    CharacterConflictORM.status == "pending",
                )
                .values(
                    status="superseded",
                    revision=CharacterConflictORM.revision + 1,
                    updated_at=now,
                )
            )
        await self.session.execute(
            update(CharacterImageSetORM)
            .where(CharacterImageSetORM.character_id == source.id)
            .values(status="draft", default_representative_image_id=None, updated_at=now)
        )
        operation = CharacterEntityOperationORM(
            id=uuid4(),
            operation_type="split",
            novel_id=source.novel_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            source_character_ids=[str(source.id)],
            target_character_ids=[str(target_ids_by_name[item.canonical_name]) for item in targets],
            action=action,
            before_snapshot=before_snapshot,
            status="completed",
            actor_id=actor_id,
            reason=reason,
            created_at=now,
            updated_at=now,
        )
        self.session.add(operation)
        self._add_manual_audit(
            operation=operation,
            subject_id=source.id,
            decision_kind="character_split",
            actor_id=actor_id,
            now=now,
        )
        await self.session.commit()
        return await self.session.get_one(CharacterEntityOperationORM, operation.id)

    async def _idempotent_operation(
        self, idempotency_key: str, request_hash: str
    ) -> CharacterEntityOperationORM | None:
        operation: CharacterEntityOperationORM | None = await self.session.scalar(
            select(CharacterEntityOperationORM).where(
                CharacterEntityOperationORM.idempotency_key == idempotency_key
            )
        )
        if operation is not None and operation.request_hash != request_hash:
            raise EntityOperationConflict("entity_operation_idempotency_conflict")
        return operation

    async def _reserve_revision(
        self, character: CharacterORM, expected_revision: int, now: datetime
    ) -> None:
        updated = await self.session.scalar(
            update(CharacterORM)
            .where(
                CharacterORM.id == character.id,
                CharacterORM.revision == expected_revision,
                CharacterORM.status == "active",
            )
            .values(revision=expected_revision + 1, updated_at=now)
            .returning(CharacterORM.id)
        )
        if updated is None:
            await self.session.rollback()
            raise EntityOperationConflict("character_revision_conflict")

    async def _entity_snapshot(self, character_ids: list[UUID]) -> dict[str, Any]:
        characters = list(
            await self.session.scalars(
                select(CharacterORM).where(CharacterORM.id.in_(character_ids))
            )
        )
        counts: dict[str, int] = {}
        count_specs: tuple[tuple[str, Any, Any], ...] = (
            ("mentions", MentionSpanORM, MentionSpanORM.resolved_character_id),
            ("observations", FeatureObservationORM, FeatureObservationORM.character_id),
            ("expressions", ExpressionObservationORM, ExpressionObservationORM.character_id),
            (
                "appearance_states",
                CharacterAppearanceStateORM,
                CharacterAppearanceStateORM.character_id,
            ),
            (
                "render_profiles",
                CharacterRenderProfileORM,
                CharacterRenderProfileORM.character_id,
            ),
            ("image_sets", CharacterImageSetORM, CharacterImageSetORM.character_id),
            ("generated_images", GeneratedImageORM, GeneratedImageORM.character_id),
        )
        for name, model, column in count_specs:
            value = await self.session.scalar(
                select(func.count()).select_from(model).where(column.in_(character_ids))
            )
            counts[name] = int(value or 0)
        return {
            "characters": [
                {
                    "id": str(item.id),
                    "canonical_name": item.canonical_name,
                    "status": item.status,
                    "revision": item.revision,
                }
                for item in characters
            ],
            "record_counts": counts,
        }

    async def _bulk_rebind(
        self, model: Any, source_ids: list[UUID], target_id: UUID, now: datetime
    ) -> None:
        await self.session.execute(
            update(model)
            .where(model.character_id.in_(source_ids))
            .values(character_id=target_id, updated_at=now)
        )

    async def _merge_conflicts(
        self, source_ids: list[UUID], target_id: UUID, now: datetime
    ) -> None:
        rows = list(
            await self.session.scalars(
                select(CharacterConflictORM).where(
                    CharacterConflictORM.character_id.in_(source_ids)
                )
            )
        )
        for row in rows:
            duplicate = await self.session.scalar(
                select(CharacterConflictORM).where(
                    CharacterConflictORM.character_id == target_id,
                    CharacterConflictORM.fingerprint == row.fingerprint,
                )
            )
            if duplicate is None:
                row.character_id = target_id
                row.updated_at = now
            else:
                duplicate.appearance_state_ids = list(
                    dict.fromkeys([*duplicate.appearance_state_ids, *row.appearance_state_ids])
                )
                duplicate.candidate_values = [
                    json.loads(item)
                    for item in dict.fromkeys(
                        _canonical(value)
                        for value in [*duplicate.candidate_values, *row.candidate_values]
                    )
                ]
                duplicate.updated_at = now
                await self.session.delete(row)

    async def _merge_event_participants(
        self, source_ids: list[UUID], target_id: UUID, now: datetime
    ) -> None:
        rows = list(
            await self.session.scalars(
                select(EventParticipantORM).where(EventParticipantORM.character_id.in_(source_ids))
            )
        )
        for row in rows:
            duplicate = await self.session.scalar(
                select(EventParticipantORM).where(
                    EventParticipantORM.event_id == row.event_id,
                    EventParticipantORM.character_id == target_id,
                    EventParticipantORM.role == row.role,
                )
            )
            if duplicate is None:
                row.character_id = target_id
                row.updated_at = now
            else:
                duplicate.evidence_observation_ids = list(
                    dict.fromkeys(
                        [*duplicate.evidence_observation_ids, *row.evidence_observation_ids]
                    )
                )
                duplicate.updated_at = now
                await self.session.delete(row)

    async def _move_render_profiles(
        self, source_ids: list[UUID], target_id: UUID, now: datetime
    ) -> None:
        maximum = await self.session.scalar(
            select(func.max(CharacterRenderProfileORM.version)).where(
                CharacterRenderProfileORM.character_id == target_id
            )
        )
        version = int(maximum or 0)
        rows = list(
            await self.session.scalars(
                select(CharacterRenderProfileORM)
                .where(CharacterRenderProfileORM.character_id.in_(source_ids))
                .order_by(CharacterRenderProfileORM.created_at, CharacterRenderProfileORM.id)
            )
        )
        for row in rows:
            version += 1
            row.character_id = target_id
            row.version = version
            row.status = "needs_review"
            row.approved_by = None
            row.approved_at = None
            row.revision += 1
            row.updated_at = now

    async def _move_image_sets(
        self, source_ids: list[UUID], target_id: UUID, now: datetime
    ) -> None:
        maximum = await self.session.scalar(
            select(func.max(CharacterImageSetORM.version)).where(
                CharacterImageSetORM.character_id == target_id
            )
        )
        version = int(maximum or 0)
        rows = list(
            await self.session.scalars(
                select(CharacterImageSetORM)
                .where(CharacterImageSetORM.character_id.in_(source_ids))
                .order_by(CharacterImageSetORM.created_at, CharacterImageSetORM.id)
            )
        )
        for row in rows:
            version += 1
            row.character_id = target_id
            row.version = version
            row.status = "draft"
            row.default_representative_image_id = None
            row.updated_at = now

    def _validate_assignment_uniqueness(self, targets: list[SplitTarget]) -> None:
        seen: dict[str, set[UUID]] = {}
        for target in targets:
            for field_name, values in target.assignments.__dict__.items():
                typed_values = list(values)
                field_seen = seen.setdefault(field_name, set())
                if len(set(typed_values)) != len(typed_values) or field_seen.intersection(
                    typed_values
                ):
                    raise ValueError("split_assignment_duplicate")
                field_seen.update(typed_values)

    async def _apply_split_assignments(
        self,
        *,
        source_character_id: UUID,
        target_character_id: UUID,
        assignments: SplitAssignments,
        now: datetime,
    ) -> None:
        ownership = (
            (MentionSpanORM, MentionSpanORM.resolved_character_id, assignments.mention_span_ids),
            (
                AliasAssertionORM,
                AliasAssertionORM.proposed_character_id,
                assignments.alias_assertion_ids,
            ),
            (
                FeatureObservationORM,
                FeatureObservationORM.character_id,
                assignments.observation_ids,
            ),
            (
                ExpressionObservationORM,
                ExpressionObservationORM.character_id,
                assignments.expression_ids,
            ),
            (
                CharacterAppearanceStateORM,
                CharacterAppearanceStateORM.character_id,
                assignments.appearance_state_ids,
            ),
            (FeatureSuggestionORM, FeatureSuggestionORM.character_id, assignments.suggestion_ids),
            (
                EventParticipantORM,
                EventParticipantORM.character_id,
                assignments.event_participant_ids,
            ),
            (SceneORM, SceneORM.point_of_view_character_id, assignments.scene_ids),
        )
        for model, owner_column, ids in ownership:
            if not ids:
                continue
            count = await self.session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.id.in_(ids), owner_column == source_character_id)
            )
            if int(count or 0) != len(ids):
                raise ValueError("split_assignment_owner_mismatch")
        if target_character_id == source_character_id:
            return
        if assignments.mention_span_ids:
            mentions = list(
                await self.session.scalars(
                    select(MentionSpanORM).where(
                        MentionSpanORM.id.in_(assignments.mention_span_ids)
                    )
                )
            )
            for mention in mentions:
                mention.resolved_character_id = target_character_id
                mention.candidate_character_ids = _replace_ids(
                    mention.candidate_character_ids, {source_character_id}, target_character_id
                )
                mention.updated_at = now
        for model, owner_column, ids in ownership[1:]:
            if ids:
                await self.session.execute(
                    update(model)
                    .where(model.id.in_(ids), owner_column == source_character_id)
                    .values({owner_column.key: target_character_id, "updated_at": now})
                )

    def _add_manual_audit(
        self,
        *,
        operation: CharacterEntityOperationORM,
        subject_id: UUID,
        decision_kind: str,
        actor_id: str,
        now: datetime,
    ) -> None:
        approval_id = uuid4()
        self.session.add_all(
            [
                DecisionRecordORM(
                    id=uuid4(),
                    pipeline_run_id=None,
                    agent_run_id=None,
                    decision_kind=decision_kind,
                    subject_type="character",
                    subject_id=subject_id,
                    decision={
                        "operation_id": str(operation.id),
                        "actor_id": actor_id,
                        "action": operation.action,
                        "before_snapshot": operation.before_snapshot,
                    },
                    evidence_ids=operation.source_character_ids,
                    source_kind="manual",
                    created_at=now,
                    updated_at=now,
                ),
                HumanApprovalORM(
                    id=approval_id,
                    pipeline_step_id=None,
                    requested_by_agent_run_id=None,
                    approval_type=decision_kind,
                    subject_type="character_entity_operation",
                    subject_id=operation.id,
                    lease_generation=0,
                    revision=1,
                    action_hash=_hash({"operation_id": str(operation.id)}),
                    action=operation.action,
                    supporting_evidence_ids=operation.source_character_ids,
                    opposing_evidence_ids=[],
                    estimated_cost=None,
                    status="approved",
                    decision="approve",
                    modifications=None,
                    resolved_by=actor_id,
                    expires_at=now,
                    resolved_at=now,
                    recovery_token_hash=_hash({"manual_approval_id": str(approval_id)}),
                    decision_payload_hash=operation.request_hash,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
