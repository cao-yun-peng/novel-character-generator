from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.domain.policies.appearance_aggregation import (
    FIELD_PERSISTENCE_POLICY_VERSION,
    REALITY_COMPATIBILITY_VERSION,
    RESOLVER_VERSION,
    VISUAL_SCHEMA_VERSION,
    AggregationObservation,
    AppearanceAggregationResult,
    aggregate_appearance,
    canonical_json,
)
from novel_character_generator.infrastructure.db.orm import (
    ChapterORM,
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterORM,
    CharacterRenderProfileORM,
    FeatureObservationORM,
    PipelineRunORM,
    PipelineStepORM,
    SceneORM,
    SourceDocumentORM,
    SourceDocumentVersionORM,
    StoryEventORM,
    TextChunkORM,
    TimelineORM,
)
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event

logger = logging.getLogger(__name__)


class AppearanceAggregationLeaseLostError(RuntimeError):
    pass


@dataclass(frozen=True)
class AggregationOutcome:
    character_id: UUID
    input_fingerprint: str
    profile_id: UUID
    profile_version: int
    profile_revision: int
    state_count: int
    open_conflict_count: int
    unchanged: bool


@dataclass(frozen=True)
class _ProtectedStateValue:
    state_id: UUID
    field_path: str
    value: Any
    temporal_scope: dict[str, Any]
    merge_priority: int


@dataclass(frozen=True)
class _ProtectedAppearance:
    profile_id: UUID | None
    identity_values: dict[str, Any]
    state_values: tuple[_ProtectedStateValue, ...]


@dataclass(frozen=True)
class _ConflictCandidate:
    field_path: str
    state_ids: tuple[str, ...]
    candidate_values: tuple[Any, ...]
    temporal_scope: dict[str, Any]
    merge_priority: int
    fingerprint_sources: tuple[str, ...]
    protects_human_confirmation: bool


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(_flatten(item, path))
        else:
            result[path] = item
    return result


def _scope_overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    domain_keys = ("timeline_id", "reality_status", "presentation_mode")
    defaults = {"reality_status": "canonical", "presentation_mode": "direct"}
    if any(
        left.get(key, defaults.get(key)) != right.get(key, defaults.get(key))
        for key in domain_keys
    ):
        return False
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
    left_event = left.get("start_event_id")
    right_event = right.get("start_event_id")
    if left_event is not None and right_event is not None:
        return bool(left_event == right_event)
    return canonical_json(left) == canonical_json(right)


def _conflict_fingerprint(
    *,
    field_path: str,
    state_ids: list[str],
    temporal_scope: dict[str, Any],
    merge_priority: int,
) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "field_path": field_path,
                "state_ids": sorted(state_ids),
                "scope": temporal_scope,
                "priority": merge_priority,
            }
        ).encode()
    ).hexdigest()


def _business_log(event_name: str, **payload: Any) -> None:
    logger.info(
        event_name,
        extra={
            "event_name": event_name,
            "event_version": "1",
            "event_id": str(uuid4()),
            "occurred_at": datetime.now(UTC).isoformat(),
            "result": payload.pop("result", "succeeded"),
            **payload,
        },
    )


class AppearanceAggregationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def source_document_version(self, novel_id: UUID) -> SourceDocumentVersionORM:
        document = await self.session.scalar(
            select(SourceDocumentVersionORM)
            .join(
                SourceDocumentORM,
                SourceDocumentVersionORM.id == SourceDocumentORM.current_version_id,
            )
            .where(SourceDocumentORM.novel_id == novel_id)
            .order_by(SourceDocumentORM.created_at.desc())
            .limit(1)
        )
        if document is None:
            raise RuntimeError("source_document_not_found")
        return document

    async def affected_character_ids(
        self, *, novel_id: UUID, source_document_version_id: UUID
    ) -> list[UUID]:
        observation_ids = set(
            await self.session.scalars(
                select(FeatureObservationORM.character_id)
                .join(CharacterORM, CharacterORM.id == FeatureObservationORM.character_id)
                .where(
                    FeatureObservationORM.source_document_version_id == source_document_version_id,
                    FeatureObservationORM.record_status == "active",
                    CharacterORM.merged_into_character_id.is_(None),
                )
                .distinct()
            )
        )
        prior_derived_ids = set(
            await self.session.scalars(
                select(CharacterAppearanceStateORM.character_id)
                .join(CharacterORM, CharacterORM.id == CharacterAppearanceStateORM.character_id)
                .where(
                    CharacterORM.novel_id == novel_id,
                    CharacterORM.merged_into_character_id.is_(None),
                    CharacterAppearanceStateORM.aggregation_fingerprint.is_not(None),
                )
                .distinct()
            )
        )
        return sorted(observation_ids | prior_derived_ids, key=str)

    async def aggregate_character(
        self,
        *,
        run: PipelineRunORM,
        step_id: UUID,
        expected_generation: int,
        character_id: UUID,
        source_document_version_id: UUID,
    ) -> AggregationOutcome:
        await self._assert_lease(step_id, expected_generation)
        character = await self.session.get(CharacterORM, character_id)
        if character is None or character.novel_id != run.novel_id:
            raise ValueError("character_not_found")
        observations = await self._observations(
            run_id=run.id,
            character_id=character_id,
            source_document_version_id=source_document_version_id,
        )
        timeline_graph_version = await self._timeline_graph_version(run.novel_id)
        result = aggregate_appearance(
            character_id=character_id,
            source_document_version_id=source_document_version_id,
            observations=observations,
            timeline_graph_version=timeline_graph_version,
        )
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="appearance.aggregation.started",
            payload={
                "step_id": str(step_id),
                "character_id": str(character_id),
                "input_fingerprint": result.input_fingerprint,
                "resolver_version": RESOLVER_VERSION,
                "lease_generation": expected_generation,
            },
        )

        latest = await self._latest_profile(character_id)
        if (
            latest is not None
            and latest.record_status == "active"
            and latest.input_fingerprint == result.input_fingerprint
        ):
            await append_run_event(
                self.session,
                run_id=run.id,
                event_type="appearance.aggregation.unchanged",
                payload={
                    "character_id": str(character_id),
                    "input_fingerprint": result.input_fingerprint,
                    "profile_revision": latest.revision,
                },
            )
            await self.session.commit()
            _business_log(
                "appearance.aggregation.unchanged",
                run_id=str(run.id),
                step_id=str(step_id),
                character_id=str(character_id),
                input_fingerprint=result.input_fingerprint,
                profile_revision=latest.revision,
            )
            return AggregationOutcome(
                character_id=character_id,
                input_fingerprint=result.input_fingerprint,
                profile_id=latest.id,
                profile_version=latest.version,
                profile_revision=latest.revision,
                state_count=len(latest.appearance_state_ids),
                open_conflict_count=len(latest.unresolved_conflicts),
                unchanged=True,
            )

        protected = await self._protected_appearance(character_id, latest)

        state_by_fingerprint = await self._persist_states(
            run_id=run.id,
            character_id=character_id,
            result=result,
        )
        conflict_summaries = await self._persist_conflicts(
            run_id=run.id,
            character_id=character_id,
            result=result,
            state_by_fingerprint=state_by_fingerprint,
            protected=protected,
        )
        profile = await self._persist_profile(
            run_id=run.id,
            character_id=character_id,
            source_document_version_id=source_document_version_id,
            result=result,
            state_by_fingerprint=state_by_fingerprint,
            conflict_summaries=conflict_summaries,
        )
        await self._assert_lease(step_id, expected_generation)
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="appearance.profile.drafted",
            payload={
                "character_id": str(character_id),
                "profile_id": str(profile.id),
                "profile_version": profile.version,
                "profile_revision": profile.revision,
                "state_count": len(state_by_fingerprint),
                "open_conflict_count": len(conflict_summaries),
            },
        )
        await self.session.commit()
        _business_log(
            "appearance.profile.drafted",
            run_id=str(run.id),
            step_id=str(step_id),
            character_id=str(character_id),
            profile_id=str(profile.id),
            profile_version=profile.version,
            profile_revision=profile.revision,
            state_count=len(state_by_fingerprint),
            open_conflict_count=len(conflict_summaries),
        )
        return AggregationOutcome(
            character_id=character_id,
            input_fingerprint=result.input_fingerprint,
            profile_id=profile.id,
            profile_version=profile.version,
            profile_revision=profile.revision,
            state_count=len(state_by_fingerprint),
            open_conflict_count=len(conflict_summaries),
            unchanged=False,
        )

    async def _assert_lease(self, step_id: UUID, expected_generation: int) -> None:
        step = await self.session.scalar(
            select(PipelineStepORM).where(PipelineStepORM.id == step_id).with_for_update()
        )
        if step is None or step.lease_generation != expected_generation or step.status != "running":
            await self.session.rollback()
            raise AppearanceAggregationLeaseLostError("step_lease_lost")

    async def _observations(
        self,
        *,
        run_id: UUID,
        character_id: UUID,
        source_document_version_id: UUID,
    ) -> list[AggregationObservation]:
        rows = list(
            await self.session.scalars(
                select(FeatureObservationORM)
                .where(
                    FeatureObservationORM.character_id == character_id,
                    FeatureObservationORM.source_document_version_id == source_document_version_id,
                    FeatureObservationORM.record_status == "active",
                    FeatureObservationORM.valid_to.is_(None),
                )
                .order_by(
                    FeatureObservationORM.field_path,
                    FeatureObservationORM.recorded_at,
                    FeatureObservationORM.id,
                )
            )
        )
        scene_ids = {row.scene_id for row in rows if row.scene_id is not None}
        scenes = {
            scene.id: scene
            for scene in (
                list(await self.session.scalars(select(SceneORM).where(SceneORM.id.in_(scene_ids))))
                if scene_ids
                else []
            )
        }
        chunk_ids = {row.source_chunk_id for row in rows if row.source_chunk_id is not None}
        chunks = {
            chunk.id: chunk
            for chunk in (
                list(
                    await self.session.scalars(
                        select(TextChunkORM).where(TextChunkORM.id.in_(chunk_ids))
                    )
                )
                if chunk_ids
                else []
            )
        }
        chapter_ids = {
            chunk.chapter_id for chunk in chunks.values() if chunk.chapter_id is not None
        }
        chapters = {
            chapter.id: chapter
            for chapter in (
                list(
                    await self.session.scalars(
                        select(ChapterORM).where(ChapterORM.id.in_(chapter_ids))
                    )
                )
                if chapter_ids
                else []
            )
        }
        observations: list[AggregationObservation] = []
        for row in rows:
            scope = dict(row.temporal_scope or {})
            scene = scenes.get(row.scene_id) if row.scene_id is not None else None
            chunk = chunks.get(row.source_chunk_id) if row.source_chunk_id is not None else None
            chapter = (
                chapters.get(chunk.chapter_id)
                if chunk is not None and chunk.chapter_id is not None
                else None
            )
            if scene is not None:
                scope.setdefault("timeline_id", str(scene.timeline_id))
                scope.setdefault("start_scene_order", scene.narrative_order)
                if scene.event_id is not None:
                    scope.setdefault("start_event_id", str(scene.event_id))
                scope.setdefault("start_chapter_ordinal", scene.chapter_ordinal)
                scope["presentation_mode"] = scene.presentation_mode
                scope["reality_status"] = scene.reality_status
            elif chapter is not None:
                scope.setdefault("start_chapter_ordinal", chapter.ordinal)
            elif row.chapter_ordinal is not None:
                scope.setdefault("start_chapter_ordinal", row.chapter_ordinal)
            observations.append(
                AggregationObservation(
                    id=row.id,
                    fingerprint=row.fingerprint,
                    field_path=row.field_path,
                    value=row.value,
                    temporal_scope=scope,
                    source_kind=row.source_kind,
                    epistemic_status=row.epistemic_status,
                    grounding_status=row.grounding_status,
                    confidence=row.confidence,
                )
            )
        return observations

    async def _timeline_graph_version(self, novel_id: UUID) -> str:
        timelines = list(
            await self.session.scalars(
                select(TimelineORM).where(TimelineORM.novel_id == novel_id).order_by(TimelineORM.id)
            )
        )
        timeline_ids = [item.id for item in timelines]
        events = (
            list(
                await self.session.scalars(
                    select(StoryEventORM)
                    .where(StoryEventORM.timeline_id.in_(timeline_ids))
                    .order_by(
                        StoryEventORM.timeline_id,
                        StoryEventORM.story_order,
                        StoryEventORM.id,
                    )
                )
            )
            if timeline_ids
            else []
        )
        payload = {
            "timelines": [
                {
                    "id": str(item.id),
                    "parent_timeline_id": str(item.parent_timeline_id)
                    if item.parent_timeline_id
                    else None,
                    "branch_event_id": str(item.branch_event_id) if item.branch_event_id else None,
                    "canonicality": item.canonicality,
                }
                for item in timelines
            ],
            "events": [
                {
                    "id": str(item.id),
                    "timeline_id": str(item.timeline_id),
                    "story_order": str(item.story_order) if item.story_order is not None else None,
                }
                for item in events
            ],
        }
        return hashlib.sha256(canonical_json(payload).encode()).hexdigest()

    async def _latest_profile(self, character_id: UUID) -> CharacterRenderProfileORM | None:
        profile: CharacterRenderProfileORM | None = await self.session.scalar(
            select(CharacterRenderProfileORM)
            .where(CharacterRenderProfileORM.character_id == character_id)
            .order_by(CharacterRenderProfileORM.version.desc())
            .limit(1)
        )
        return profile

    async def _protected_appearance(
        self,
        character_id: UUID,
        latest: CharacterRenderProfileORM | None,
    ) -> _ProtectedAppearance:
        confirmed = await self.session.scalar(
            select(CharacterRenderProfileORM)
            .where(
                CharacterRenderProfileORM.character_id == character_id,
                CharacterRenderProfileORM.status.in_(("approved", "locked")),
            )
            .order_by(CharacterRenderProfileORM.version.desc())
            .limit(1)
        )
        identity_values = _flatten(confirmed.identity_anchor) if confirmed is not None else {}
        if latest is not None:
            latest_identity = _flatten(latest.identity_anchor)
            for path, source_ids in latest.field_sources.items():
                if any(str(item).startswith("manual:") for item in source_ids):
                    if path in latest_identity:
                        identity_values[path] = latest_identity[path]

        profile_state_ids: set[UUID] = set()
        if confirmed is not None:
            profile_state_ids.update(UUID(item) for item in confirmed.appearance_state_ids)
        if latest is not None:
            profile_state_ids.update(UUID(item) for item in latest.appearance_state_ids)
        states = (
            list(
                await self.session.scalars(
                    select(CharacterAppearanceStateORM).where(
                        CharacterAppearanceStateORM.id.in_(profile_state_ids)
                    )
                )
            )
            if profile_state_ids
            else []
        )
        confirmed_ids = (
            {UUID(item) for item in confirmed.appearance_state_ids}
            if confirmed is not None
            else set()
        )
        protected: list[_ProtectedStateValue] = []
        manual: list[_ProtectedStateValue] = []
        for state in states:
            if state.state_kind == "manual_override":
                if state.record_status != "active":
                    continue
                target = manual
            else:
                if state.id not in confirmed_ids:
                    continue
                target = protected
            for path, value in _flatten(state.appearance).items():
                target.append(
                    _ProtectedStateValue(
                        state_id=state.id,
                        field_path=path,
                        value=value,
                        temporal_scope=state.temporal_scope,
                        merge_priority=state.merge_priority,
                    )
                )
        for manual_value in manual:
            protected = [
                item
                for item in protected
                if not (
                    item.field_path == manual_value.field_path
                    and _scope_overlaps(item.temporal_scope, manual_value.temporal_scope)
                )
            ]
            protected.append(manual_value)
        return _ProtectedAppearance(
            profile_id=confirmed.id if confirmed is not None else None,
            identity_values=identity_values,
            state_values=tuple(protected),
        )

    async def _persist_states(
        self,
        *,
        run_id: UUID,
        character_id: UUID,
        result: AppearanceAggregationResult,
    ) -> dict[str, CharacterAppearanceStateORM]:
        fingerprints = [item.fingerprint for item in result.states]
        existing_rows = (
            list(
                await self.session.scalars(
                    select(CharacterAppearanceStateORM).where(
                        CharacterAppearanceStateORM.aggregation_fingerprint.in_(fingerprints)
                    )
                )
            )
            if fingerprints
            else []
        )
        by_fingerprint = {
            row.aggregation_fingerprint: row
            for row in existing_rows
            if row.aggregation_fingerprint is not None
        }
        now = datetime.now(UTC)
        for derived in result.states:
            row = by_fingerprint.get(derived.fingerprint)
            if row is None:
                row = CharacterAppearanceStateORM(
                    id=uuid4(),
                    character_id=character_id,
                    temporal_scope=derived.temporal_scope,
                    label=derived.label,
                    state_kind=derived.state_kind,
                    merge_priority=derived.merge_priority,
                    age_stage=derived.age_stage,
                    appearance=derived.appearance,
                    field_sources=derived.field_sources,
                    resolver_version=RESOLVER_VERSION,
                    aggregation_fingerprint=derived.fingerprint,
                    created_by_run_id=run_id,
                    record_status="active",
                    status="draft",
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(row)
                by_fingerprint[derived.fingerprint] = row
                await append_run_event(
                    self.session,
                    run_id=run_id,
                    event_type="appearance.state.derived",
                    payload={
                        "state_id": str(row.id),
                        "character_id": str(character_id),
                        "scope": derived.temporal_scope,
                        "field_count": len(derived.field_sources),
                        "source_count": sum(len(ids) for ids in derived.field_sources.values()),
                    },
                )
            else:
                row.record_status = "active"
                row.updated_at = now
        prior_auto = list(
            await self.session.scalars(
                select(CharacterAppearanceStateORM).where(
                    CharacterAppearanceStateORM.character_id == character_id,
                    CharacterAppearanceStateORM.aggregation_fingerprint.is_not(None),
                    CharacterAppearanceStateORM.record_status.in_(("active", "invalidated")),
                )
            )
        )
        current_ids = {row.id for row in by_fingerprint.values()}
        for row in prior_auto:
            if row.id not in current_ids:
                row.record_status = "superseded"
                row.updated_at = now
        await self.session.flush()
        return by_fingerprint

    async def _persist_conflicts(
        self,
        *,
        run_id: UUID,
        character_id: UUID,
        result: AppearanceAggregationResult,
        state_by_fingerprint: dict[str, CharacterAppearanceStateORM],
        protected: _ProtectedAppearance,
    ) -> list[dict[str, Any]]:
        existing = list(
            await self.session.scalars(
                select(CharacterConflictORM).where(
                    CharacterConflictORM.character_id == character_id,
                    CharacterConflictORM.status == "pending",
                )
            )
        )
        auto_state_ids = set(
            await self.session.scalars(
                select(CharacterAppearanceStateORM.id).where(
                    CharacterAppearanceStateORM.character_id == character_id,
                    CharacterAppearanceStateORM.aggregation_fingerprint.is_not(None),
                )
            )
        )
        now = datetime.now(UTC)
        detected: dict[str, _ConflictCandidate] = {}
        auto_conflict_domains: set[tuple[str, str]] = set()
        for derived_conflict in result.conflicts:
            conflict_state_ids = [
                str(state_by_fingerprint[item].id)
                for item in derived_conflict.state_fingerprints
            ]
            candidate = _ConflictCandidate(
                field_path=derived_conflict.field_path,
                state_ids=tuple(conflict_state_ids),
                candidate_values=derived_conflict.candidate_values,
                temporal_scope=derived_conflict.temporal_scope,
                merge_priority=derived_conflict.merge_priority,
                fingerprint_sources=tuple(conflict_state_ids),
                protects_human_confirmation=False,
            )
            fingerprint = _conflict_fingerprint(
                field_path=candidate.field_path,
                state_ids=list(candidate.fingerprint_sources),
                temporal_scope=candidate.temporal_scope,
                merge_priority=candidate.merge_priority,
            )
            detected[fingerprint] = candidate
            auto_conflict_domains.add(
                (
                    derived_conflict.field_path,
                    canonical_json(derived_conflict.temporal_scope),
                )
            )

        for derived_state in result.states:
            derived_row = state_by_fingerprint[derived_state.fingerprint]
            derived_values = _flatten(derived_state.appearance)
            for protected_value in protected.state_values:
                if protected_value.field_path not in derived_values:
                    continue
                if not _scope_overlaps(
                    protected_value.temporal_scope, derived_state.temporal_scope
                ):
                    continue
                new_value = derived_values[protected_value.field_path]
                if canonical_json(protected_value.value) == canonical_json(new_value):
                    continue
                domain = (
                    protected_value.field_path,
                    canonical_json(derived_state.temporal_scope),
                )
                if domain in auto_conflict_domains:
                    continue
                protected_state_ids = (str(protected_value.state_id), str(derived_row.id))
                candidate = _ConflictCandidate(
                    field_path=protected_value.field_path,
                    state_ids=protected_state_ids,
                    candidate_values=(protected_value.value, new_value),
                    temporal_scope=derived_state.temporal_scope,
                    merge_priority=max(
                        protected_value.merge_priority, derived_state.merge_priority
                    ),
                    fingerprint_sources=protected_state_ids,
                    protects_human_confirmation=True,
                )
                fingerprint = _conflict_fingerprint(
                    field_path=candidate.field_path,
                    state_ids=list(candidate.fingerprint_sources),
                    temporal_scope=candidate.temporal_scope,
                    merge_priority=candidate.merge_priority,
                )
                detected[fingerprint] = candidate

        derived_identity = _flatten(result.identity_anchor)
        identity_scope = {
            "scope_type": "identity",
            "reality_status": "canonical",
            "presentation_mode": "direct",
        }
        for field_path in sorted(protected.identity_values.keys() & derived_identity.keys()):
            protected_value = protected.identity_values[field_path]
            new_value = derived_identity[field_path]
            if canonical_json(protected_value) == canonical_json(new_value):
                continue
            fingerprint_sources = (
                "confirmed:"
                f"{protected.profile_id}:{field_path}:"
                f"{hashlib.sha256(canonical_json(protected_value).encode()).hexdigest()}",
                "derived:"
                f"{result.input_fingerprint}:{field_path}:"
                f"{hashlib.sha256(canonical_json(new_value).encode()).hexdigest()}",
            )
            candidate = _ConflictCandidate(
                field_path=field_path,
                state_ids=(),
                candidate_values=(protected_value, new_value),
                temporal_scope=identity_scope,
                merge_priority=1_000,
                fingerprint_sources=fingerprint_sources,
                protects_human_confirmation=True,
            )
            fingerprint = _conflict_fingerprint(
                field_path=candidate.field_path,
                state_ids=list(candidate.fingerprint_sources),
                temporal_scope=candidate.temporal_scope,
                merge_priority=candidate.merge_priority,
            )
            detected[fingerprint] = candidate
        existing_by_fingerprint = {row.fingerprint: row for row in existing}
        latest = await self._latest_profile(character_id)
        managed_conflict_ids = {
            UUID(str(item["conflict_id"]))
            for item in (latest.unresolved_conflicts if latest is not None else [])
            if item.get("conflict_id") is not None
        }
        for row in existing:
            related_ids = {UUID(item) for item in row.appearance_state_ids}
            if row.fingerprint not in detected and (
                related_ids & auto_state_ids or row.id in managed_conflict_ids
            ):
                row.status = "superseded"
                row.revision += 1
                row.updated_at = now
        summaries: list[dict[str, Any]] = []
        for fingerprint, candidate in sorted(detected.items()):
            conflict_row = existing_by_fingerprint.get(fingerprint)
            if conflict_row is None:
                conflict_row = CharacterConflictORM(
                    id=uuid4(),
                    character_id=character_id,
                    field_path=candidate.field_path,
                    appearance_state_ids=list(candidate.state_ids),
                    candidate_values=list(candidate.candidate_values),
                    temporal_scope=candidate.temporal_scope,
                    merge_priority=candidate.merge_priority,
                    conflict_kind=(
                        "human_confirmation"
                        if candidate.protects_human_confirmation
                        else "incompatible_values"
                    ),
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
                await append_run_event(
                    self.session,
                    run_id=run_id,
                    event_type="appearance.conflict.detected",
                    payload={
                        "conflict_id": str(conflict_row.id),
                        "character_id": str(character_id),
                        "field_path": conflict_row.field_path,
                        "appearance_state_ids": list(candidate.state_ids),
                        "scope": conflict_row.temporal_scope,
                        "protects_human_confirmation": candidate.protects_human_confirmation,
                    },
                )
            else:
                conflict_row.appearance_state_ids = list(candidate.state_ids)
                conflict_row.candidate_values = list(candidate.candidate_values)
                conflict_row.temporal_scope = candidate.temporal_scope
                conflict_row.merge_priority = candidate.merge_priority
                conflict_row.conflict_kind = (
                    "human_confirmation"
                    if candidate.protects_human_confirmation
                    else "incompatible_values"
                )
                conflict_row.updated_at = now
            summaries.append(
                {
                    "conflict_id": str(conflict_row.id),
                    "field_path": conflict_row.field_path,
                    "appearance_state_ids": conflict_row.appearance_state_ids,
                    "candidate_values": conflict_row.candidate_values,
                    "protects_human_confirmation": candidate.protects_human_confirmation,
                }
            )
        await self.session.flush()
        return summaries

    async def _persist_profile(
        self,
        *,
        run_id: UUID,
        character_id: UUID,
        source_document_version_id: UUID,
        result: AppearanceAggregationResult,
        state_by_fingerprint: dict[str, CharacterAppearanceStateORM],
        conflict_summaries: list[dict[str, Any]],
    ) -> CharacterRenderProfileORM:
        latest = await self._latest_profile(character_id)
        now = datetime.now(UTC)
        derived_ids = [state_by_fingerprint[item.fingerprint].id for item in result.states]
        previous_states: list[CharacterAppearanceStateORM] = []
        if latest is not None and latest.appearance_state_ids:
            previous_ids = [UUID(item) for item in latest.appearance_state_ids]
            previous_states = list(
                await self.session.scalars(
                    select(CharacterAppearanceStateORM).where(
                        CharacterAppearanceStateORM.id.in_(previous_ids)
                    )
                )
            )
        manual_ids = [
            item.id
            for item in previous_states
            if item.aggregation_fingerprint is None and item.record_status == "active"
        ]
        state_ids = list(dict.fromkeys([*manual_ids, *derived_ids]))
        metadata = {
            "resolver_version": RESOLVER_VERSION,
            "reality_compatibility_version": REALITY_COMPATIBILITY_VERSION,
            "field_persistence_policy_version": FIELD_PERSISTENCE_POLICY_VERSION,
            "visual_schema_version": VISUAL_SCHEMA_VERSION,
        }
        status = "needs_review" if conflict_summaries else "draft"
        if latest is None:
            profile = CharacterRenderProfileORM(
                id=uuid4(),
                character_id=character_id,
                version=1,
                status=status,
                identity_anchor=result.identity_anchor,
                default_appearance_state_id=state_ids[0] if len(state_ids) == 1 else None,
                default_stage_key=None,
                appearance_state_ids=[str(item) for item in state_ids],
                palette={},
                field_sources=result.identity_sources,
                field_suggestions={},
                unresolved_conflicts=conflict_summaries,
                style_preset="illustration-v1",
                approved_by=None,
                approved_at=None,
                revision=1,
                record_status="active",
                input_fingerprint=result.input_fingerprint,
                source_document_version_id=source_document_version_id,
                aggregation_run_id=run_id,
                aggregation_metadata=metadata,
                created_at=now,
                updated_at=now,
            )
            self.session.add(profile)
        elif latest.status in {"approved", "locked"}:
            profile = CharacterRenderProfileORM(
                id=uuid4(),
                character_id=character_id,
                version=latest.version + 1,
                status=status,
                identity_anchor=_deep_merge(result.identity_anchor, latest.identity_anchor),
                default_appearance_state_id=state_ids[0] if len(state_ids) == 1 else None,
                default_stage_key=latest.default_stage_key,
                appearance_state_ids=[str(item) for item in state_ids],
                palette=latest.palette,
                field_sources={**result.identity_sources, **latest.field_sources},
                field_suggestions=latest.field_suggestions,
                unresolved_conflicts=conflict_summaries,
                style_preset=latest.style_preset,
                approved_by=None,
                approved_at=None,
                revision=latest.revision + 1,
                record_status="active",
                input_fingerprint=result.input_fingerprint,
                source_document_version_id=source_document_version_id,
                aggregation_run_id=run_id,
                aggregation_metadata=metadata,
                created_at=now,
                updated_at=now,
            )
            self.session.add(profile)
        else:
            profile = latest
            profile.status = status
            profile.identity_anchor = _deep_merge(result.identity_anchor, profile.identity_anchor)
            profile.default_appearance_state_id = state_ids[0] if len(state_ids) == 1 else None
            profile.appearance_state_ids = [str(item) for item in state_ids]
            profile.field_sources = {**result.identity_sources, **profile.field_sources}
            profile.unresolved_conflicts = conflict_summaries
            profile.approved_by = None
            profile.approved_at = None
            profile.record_status = "active"
            profile.revision += 1
            profile.input_fingerprint = result.input_fingerprint
            profile.source_document_version_id = source_document_version_id
            profile.aggregation_run_id = run_id
            profile.aggregation_metadata = metadata
            profile.updated_at = now
        await self.session.flush()
        return profile
