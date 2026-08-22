from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.infrastructure.db.orm import (
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterORM,
    CharacterRenderProfileORM,
    SceneORM,
    StoryEventORM,
    TimelineORM,
)

STATE_KIND_ORDER = {
    "base_age_stage": 0,
    "persistent_change": 1,
    "disguise": 2,
    "clothing": 3,
    "temporary_condition": 4,
    "manual_override": 5,
}


class AppearanceRevisionConflict(RuntimeError):
    pass


class AppearanceResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderProfileUpdate:
    identity_anchor: dict[str, Any]
    default_stage_key: str | None
    appearance_state_ids: list[UUID]
    palette: dict[str, Any]
    field_sources: dict[str, list[str]]
    field_suggestions: dict[str, Any]
    style_preset: str


@dataclass(frozen=True)
class SnapshotTarget:
    timeline_id: UUID | None = None
    event_id: UUID | None = None
    scene_id: UUID | None = None
    chapter_ordinal: int | None = None


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(_flatten(item, path))
        else:
            result[path] = item
    return result


def _put_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cursor = target
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    cursor[parts[-1]] = value


def _scope_overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("timeline_id") != right.get("timeline_id"):
        return False
    if left.get("reality_status", "canonical") != right.get("reality_status", "canonical"):
        return False
    left_type = left.get("scope_type", "unknown")
    right_type = right.get("scope_type", "unknown")
    if "unknown" in {left_type, right_type}:
        return _canonical(left) == _canonical(right)
    if left_type == right_type == "instant":
        left_event = left.get("start_event_id")
        right_event = right.get("start_event_id")
        if left_event and right_event:
            return bool(left_event == right_event)
    left_start = left.get("start_chapter_ordinal")
    left_end = left.get("end_chapter_ordinal")
    right_start = right.get("start_chapter_ordinal")
    right_end = right.get("end_chapter_ordinal")
    if any(item is not None for item in (left_start, left_end, right_start, right_end)):
        low_left = int(left_start) if left_start is not None else -1
        high_left = int(left_end) if left_end is not None else 2**31
        low_right = int(right_start) if right_start is not None else -1
        high_right = int(right_end) if right_end is not None else 2**31
        return max(low_left, low_right) <= min(high_left, high_right)
    return True


class AppearanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def character(self, character_id: UUID) -> CharacterORM | None:
        return await self.session.get(CharacterORM, character_id)

    async def states(self, character_id: UUID) -> list[CharacterAppearanceStateORM]:
        return list(
            await self.session.scalars(
                select(CharacterAppearanceStateORM)
                .where(
                    CharacterAppearanceStateORM.character_id == character_id,
                    CharacterAppearanceStateORM.record_status == "active",
                )
                .order_by(
                    CharacterAppearanceStateORM.merge_priority,
                    CharacterAppearanceStateORM.created_at,
                    CharacterAppearanceStateORM.id,
                )
            )
        )

    async def latest_profile(self, character_id: UUID) -> CharacterRenderProfileORM | None:
        profile: CharacterRenderProfileORM | None = await self.session.scalar(
            select(CharacterRenderProfileORM)
            .where(CharacterRenderProfileORM.character_id == character_id)
            .order_by(CharacterRenderProfileORM.version.desc())
            .limit(1)
        )
        return profile

    async def conflicts(self, character_id: UUID) -> list[CharacterConflictORM]:
        return list(
            await self.session.scalars(
                select(CharacterConflictORM)
                .where(CharacterConflictORM.character_id == character_id)
                .order_by(CharacterConflictORM.status, CharacterConflictORM.created_at)
            )
        )

    async def put_profile(
        self,
        character_id: UUID,
        *,
        request: RenderProfileUpdate,
        expected_revision: int,
    ) -> CharacterRenderProfileORM:
        if await self.character(character_id) is None:
            raise ValueError("character_not_found")
        state_ids = list(dict.fromkeys(request.appearance_state_ids))
        states = await self._require_states(character_id, state_ids)
        profile = await self.latest_profile(character_id)
        now = datetime.now(UTC)
        if profile is None:
            if expected_revision != 0:
                raise AppearanceRevisionConflict("render_profile_revision_conflict")
            profile = CharacterRenderProfileORM(
                id=uuid4(),
                character_id=character_id,
                version=1,
                status="draft",
                identity_anchor=request.identity_anchor,
                default_appearance_state_id=state_ids[0] if len(state_ids) == 1 else None,
                default_stage_key=request.default_stage_key,
                appearance_state_ids=[str(item) for item in state_ids],
                palette=request.palette,
                field_sources=request.field_sources,
                field_suggestions=request.field_suggestions,
                unresolved_conflicts=[],
                style_preset=request.style_preset,
                approved_by=None,
                approved_at=None,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            self.session.add(profile)
        elif profile.revision != expected_revision:
            raise AppearanceRevisionConflict("render_profile_revision_conflict")
        elif profile.status in {"approved", "locked"}:
            next_revision = profile.revision + 1
            profile = CharacterRenderProfileORM(
                id=uuid4(),
                character_id=character_id,
                version=profile.version + 1,
                status="draft",
                identity_anchor=request.identity_anchor,
                default_appearance_state_id=state_ids[0] if len(state_ids) == 1 else None,
                default_stage_key=request.default_stage_key,
                appearance_state_ids=[str(item) for item in state_ids],
                palette=request.palette,
                field_sources=request.field_sources,
                field_suggestions=request.field_suggestions,
                unresolved_conflicts=[],
                style_preset=request.style_preset,
                approved_by=None,
                approved_at=None,
                revision=next_revision,
                created_at=now,
                updated_at=now,
            )
            self.session.add(profile)
        else:
            profile.identity_anchor = request.identity_anchor
            profile.default_appearance_state_id = state_ids[0] if len(state_ids) == 1 else None
            profile.default_stage_key = request.default_stage_key
            profile.appearance_state_ids = [str(item) for item in state_ids]
            profile.palette = request.palette
            profile.field_sources = request.field_sources
            profile.field_suggestions = request.field_suggestions
            profile.style_preset = request.style_preset
            profile.revision += 1
            profile.updated_at = now
        profile.unresolved_conflicts = await self._refresh_conflicts(character_id, states, now)
        if profile.unresolved_conflicts:
            profile.status = "needs_review"
        else:
            profile.status = "draft"
        await self.session.commit()
        return await self.session.get_one(CharacterRenderProfileORM, profile.id)

    async def approve(
        self, character_id: UUID, *, expected_revision: int, actor_id: str
    ) -> CharacterRenderProfileORM:
        profile = await self.latest_profile(character_id)
        if profile is None:
            raise ValueError("render_profile_not_found")
        if profile.revision != expected_revision:
            raise AppearanceRevisionConflict("render_profile_revision_conflict")
        pending = await self.session.scalar(
            select(CharacterConflictORM.id)
            .where(
                CharacterConflictORM.character_id == character_id,
                CharacterConflictORM.status == "pending",
            )
            .limit(1)
        )
        if pending is not None or profile.unresolved_conflicts:
            raise AppearanceResolutionError("appearance_conflicts_unresolved")
        states = await self._require_states(
            character_id, [UUID(item) for item in profile.appearance_state_ids]
        )
        now = datetime.now(UTC)
        for state in states:
            state.status = "approved"
            state.updated_at = now
        profile.status = "approved"
        profile.approved_by = actor_id
        profile.approved_at = now
        profile.revision += 1
        profile.updated_at = now
        await self.session.commit()
        return await self.session.get_one(CharacterRenderProfileORM, profile.id)

    async def resolve_conflict(
        self,
        conflict_id: UUID,
        *,
        selected_value: Any,
        expected_revision: int,
        actor_id: str,
    ) -> CharacterConflictORM:
        conflict = await self.session.get(CharacterConflictORM, conflict_id)
        if conflict is None:
            raise ValueError("appearance_conflict_not_found")
        if conflict.status != "pending":
            raise AppearanceResolutionError("appearance_conflict_already_resolved")
        now = datetime.now(UTC)
        updated = await self.session.scalar(
            update(CharacterConflictORM)
            .where(
                CharacterConflictORM.id == conflict_id,
                CharacterConflictORM.revision == expected_revision,
                CharacterConflictORM.status == "pending",
            )
            .values(
                status="resolved",
                resolution={"field_path": conflict.field_path, "selected_value": selected_value},
                resolved_by=actor_id,
                resolved_at=now,
                revision=expected_revision + 1,
                updated_at=now,
            )
            .returning(CharacterConflictORM.id)
        )
        if updated is None:
            await self.session.rollback()
            raise AppearanceRevisionConflict("appearance_conflict_revision_conflict")
        override: dict[str, Any] = {}
        _put_path(override, conflict.field_path, selected_value)
        state = CharacterAppearanceStateORM(
            id=uuid4(),
            character_id=conflict.character_id,
            temporal_scope=conflict.temporal_scope,
            label=f"Conflict resolution: {conflict.field_path}",
            state_kind="manual_override",
            merge_priority=max(1000, conflict.merge_priority + 1),
            age_stage=None,
            appearance=override,
            field_sources={},
            resolver_version="appearance-resolver-v1",
            created_by_run_id=None,
            record_status="active",
            status="approved",
            created_at=now,
            updated_at=now,
        )
        self.session.add(state)
        profile = await self.latest_profile(conflict.character_id)
        if profile is not None:
            profile.appearance_state_ids = [*profile.appearance_state_ids, str(state.id)]
            profile.unresolved_conflicts = [
                item
                for item in profile.unresolved_conflicts
                if item.get("conflict_id") != str(conflict_id)
            ]
            profile.revision += 1
            profile.status = "needs_review" if profile.unresolved_conflicts else "draft"
            profile.approved_by = None
            profile.approved_at = None
            profile.updated_at = now
        await self.session.commit()
        return await self.session.get_one(CharacterConflictORM, conflict_id)

    async def snapshot(self, character_id: UUID, *, target: SnapshotTarget) -> dict[str, Any]:
        character = await self.character(character_id)
        if character is None:
            raise ValueError("character_not_found")
        profile = await self.latest_profile(character_id)
        if profile is None:
            raise ValueError("render_profile_not_found")
        states = await self._require_states(
            character_id, [UUID(item) for item in profile.appearance_state_ids]
        )
        states = [
            state
            for state in states
            if state.status == "approved" and state.record_status == "active"
        ]
        resolved_target = await self._resolve_target(character, target)
        if all(
            value is None
            for value in (
                resolved_target.timeline_id,
                resolved_target.event_id,
                resolved_target.scene_id,
                resolved_target.chapter_ordinal,
            )
        ):
            if len(states) > 1:
                raise AppearanceResolutionError("ambiguous_appearance_state")
            selected = states
        else:
            selected = await self._states_at_target(states, resolved_target)
        selected.sort(
            key=lambda item: (
                STATE_KIND_ORDER.get(item.state_kind, 99),
                item.merge_priority,
                item.created_at,
                str(item.id),
            )
        )
        resolved = dict(profile.identity_anchor)
        sources: dict[str, list[str]] = dict(profile.field_sources)
        precedence_values: dict[tuple[int, int, str], str] = {}
        manual_override_paths = {
            path
            for state in selected
            if state.state_kind == "manual_override"
            for path in _flatten(state.appearance)
        }
        for state in selected:
            rank = STATE_KIND_ORDER.get(state.state_kind, 99)
            for path, value in _flatten(state.appearance).items():
                key = (rank, state.merge_priority, path)
                canonical_value = _canonical(value)
                previous = precedence_values.get(key)
                if (
                    previous is not None
                    and previous != canonical_value
                    and path not in manual_override_paths
                ):
                    raise AppearanceResolutionError("appearance_conflicts_unresolved")
                precedence_values[key] = canonical_value
                _put_path(resolved, path, value)
                if path in state.field_sources:
                    sources[path] = state.field_sources[path]
        payload = {
            "character_id": str(character_id),
            "render_profile_id": str(profile.id),
            "render_profile_version": profile.version,
            "target": {
                "timeline_id": str(resolved_target.timeline_id)
                if resolved_target.timeline_id
                else None,
                "event_id": str(resolved_target.event_id) if resolved_target.event_id else None,
                "scene_id": str(resolved_target.scene_id) if resolved_target.scene_id else None,
                "chapter_ordinal": resolved_target.chapter_ordinal,
            },
            "appearance_state_ids": [str(item.id) for item in selected],
            "appearance": resolved,
            "palette": profile.palette,
            "style_preset": profile.style_preset,
            "field_sources": sources,
            "resolver_version": "appearance-resolver-v1",
        }
        payload["snapshot_hash"] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
        return payload

    async def _require_states(
        self, character_id: UUID, state_ids: list[UUID]
    ) -> list[CharacterAppearanceStateORM]:
        if not state_ids:
            return []
        rows = list(
            await self.session.scalars(
                select(CharacterAppearanceStateORM).where(
                    CharacterAppearanceStateORM.id.in_(state_ids),
                    CharacterAppearanceStateORM.character_id == character_id,
                )
            )
        )
        by_id = {item.id: item for item in rows}
        if any(item not in by_id for item in state_ids):
            raise ValueError("appearance_state_character_mismatch")
        return [by_id[item] for item in state_ids]

    async def _refresh_conflicts(
        self,
        character_id: UUID,
        states: list[CharacterAppearanceStateORM],
        now: datetime,
    ) -> list[dict[str, Any]]:
        detected: dict[str, dict[str, Any]] = {}
        for index, left in enumerate(states):
            left_values = _flatten(left.appearance)
            for right in states[index + 1 :]:
                if STATE_KIND_ORDER.get(left.state_kind) != STATE_KIND_ORDER.get(right.state_kind):
                    continue
                if left.merge_priority != right.merge_priority:
                    continue
                if not _scope_overlaps(left.temporal_scope, right.temporal_scope):
                    continue
                right_values = _flatten(right.appearance)
                for path in sorted(left_values.keys() & right_values.keys()):
                    if _canonical(left_values[path]) == _canonical(right_values[path]):
                        continue
                    state_ids = sorted([str(left.id), str(right.id)])
                    fingerprint = hashlib.sha256(
                        _canonical(
                            {
                                "field_path": path,
                                "state_ids": state_ids,
                                "scope": left.temporal_scope,
                                "priority": left.merge_priority,
                            }
                        ).encode()
                    ).hexdigest()
                    detected[fingerprint] = {
                        "field_path": path,
                        "state_ids": state_ids,
                        "candidate_values": [left_values[path], right_values[path]],
                        "temporal_scope": left.temporal_scope,
                        "merge_priority": left.merge_priority,
                    }
        existing = list(
            await self.session.scalars(
                select(CharacterConflictORM).where(
                    CharacterConflictORM.character_id == character_id,
                    CharacterConflictORM.status == "pending",
                )
            )
        )
        by_fingerprint = {item.fingerprint: item for item in existing}
        for existing_row in existing:
            if existing_row.fingerprint not in detected:
                existing_row.status = "superseded"
                existing_row.revision += 1
                existing_row.updated_at = now
        summaries: list[dict[str, Any]] = []
        for fingerprint, item in detected.items():
            conflict_row = by_fingerprint.get(fingerprint)
            if conflict_row is None:
                conflict_row = CharacterConflictORM(
                    id=uuid4(),
                    character_id=character_id,
                    field_path=item["field_path"],
                    appearance_state_ids=item["state_ids"],
                    candidate_values=item["candidate_values"],
                    temporal_scope=item["temporal_scope"],
                    merge_priority=item["merge_priority"],
                    fingerprint=fingerprint,
                    status="pending",
                    resolution=None,
                    resolved_by=None,
                    resolved_at=None,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(conflict_row)
            summaries.append(
                {
                    "conflict_id": str(conflict_row.id),
                    "field_path": conflict_row.field_path,
                    "appearance_state_ids": conflict_row.appearance_state_ids,
                    "candidate_values": conflict_row.candidate_values,
                }
            )
        return summaries

    async def _resolve_target(
        self, character: CharacterORM, target: SnapshotTarget
    ) -> SnapshotTarget:
        if target.scene_id is not None:
            scene = await self.session.get(SceneORM, target.scene_id)
            if scene is None:
                raise ValueError("scene_not_found")
            if scene.novel_id != character.novel_id:
                raise ValueError("scene_character_novel_mismatch")
            return SnapshotTarget(
                timeline_id=scene.timeline_id,
                event_id=scene.event_id,
                scene_id=scene.id,
                chapter_ordinal=scene.chapter_ordinal,
            )
        if target.event_id is not None:
            event = await self.session.get(StoryEventORM, target.event_id)
            if event is None:
                raise ValueError("event_not_found")
            timeline = await self.session.get_one(TimelineORM, event.timeline_id)
            if timeline.novel_id != character.novel_id:
                raise ValueError("event_character_novel_mismatch")
            if target.timeline_id is not None and target.timeline_id != event.timeline_id:
                raise ValueError("event_timeline_mismatch")
            return SnapshotTarget(
                timeline_id=event.timeline_id,
                event_id=event.id,
                chapter_ordinal=target.chapter_ordinal,
            )
        if target.timeline_id is not None:
            target_timeline = await self.session.get(TimelineORM, target.timeline_id)
            if target_timeline is None:
                raise ValueError("timeline_not_found")
            if target_timeline.novel_id != character.novel_id:
                raise ValueError("timeline_character_novel_mismatch")
        return target

    async def _states_at_target(
        self, states: list[CharacterAppearanceStateORM], target: SnapshotTarget
    ) -> list[CharacterAppearanceStateORM]:
        if target.timeline_id is None:
            raise AppearanceResolutionError("target_timeline_required")
        timeline_limits = await self._timeline_limits(target.timeline_id, target.event_id)
        event_orders: dict[UUID, Decimal | None] = {}
        selected: list[CharacterAppearanceStateORM] = []
        for state in states:
            scope = state.temporal_scope
            if scope.get("reality_status", "canonical") != "canonical":
                continue
            try:
                state_timeline = UUID(str(scope["timeline_id"]))
            except (KeyError, ValueError):
                continue
            if state_timeline not in timeline_limits:
                continue
            if scope.get("scope_type") == "unknown":
                continue
            chapter = target.chapter_ordinal
            start_chapter = scope.get("start_chapter_ordinal")
            end_chapter = scope.get("end_chapter_ordinal")
            if start_chapter is not None and (chapter is None or chapter < int(start_chapter)):
                continue
            if end_chapter is not None and (chapter is None or chapter > int(end_chapter)):
                continue
            target_order = timeline_limits[state_timeline]
            start_event = scope.get("start_event_id")
            end_event = scope.get("end_event_id")
            if start_event is not None:
                start_id = UUID(str(start_event))
                if start_id not in event_orders:
                    event = await self.session.get(StoryEventORM, start_id)
                    event_orders[start_id] = event.story_order if event is not None else None
                start_order = event_orders[start_id]
                if target_order is None or start_order is None or start_order > target_order:
                    continue
            if end_event is not None:
                end_id = UUID(str(end_event))
                if end_id not in event_orders:
                    event = await self.session.get(StoryEventORM, end_id)
                    event_orders[end_id] = event.story_order if event is not None else None
                end_order = event_orders[end_id]
                if target_order is None or end_order is None or end_order < target_order:
                    continue
            selected.append(state)
        return selected

    async def _timeline_limits(
        self, timeline_id: UUID, event_id: UUID | None
    ) -> dict[UUID, Decimal | None]:
        target_order: Decimal | None = None
        if event_id is not None:
            event = await self.session.get(StoryEventORM, event_id)
            if event is None or event.timeline_id != timeline_id:
                raise ValueError("event_timeline_mismatch")
            target_order = event.story_order
        limits: dict[UUID, Decimal | None] = {timeline_id: target_order}
        current = await self.session.get_one(TimelineORM, timeline_id)
        visited = {current.id}
        while current.parent_timeline_id is not None:
            parent_id = current.parent_timeline_id
            if parent_id in visited:
                raise AppearanceResolutionError("timeline_cycle_detected")
            branch_order: Decimal | None = None
            if current.branch_event_id is not None:
                branch = await self.session.get(StoryEventORM, current.branch_event_id)
                if branch is None or branch.timeline_id != parent_id:
                    raise AppearanceResolutionError("invalid_timeline_branch_event")
                branch_order = branch.story_order
            limits[parent_id] = branch_order
            current = await self.session.get_one(TimelineORM, parent_id)
            visited.add(parent_id)
        return limits
