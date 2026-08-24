from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

RESOLVER_VERSION = "appearance-resolver-v2"
REALITY_COMPATIBILITY_VERSION = "reality-compatibility-v1"
FIELD_PERSISTENCE_POLICY_VERSION = "appearance-persistence-v1"
VISUAL_SCHEMA_VERSION = "visual-schema-v1"

ALLOWED_VISUAL_ROOTS = {
    "accessory",
    "accessories",
    "age",
    "age_stage",
    "body",
    "cleanliness",
    "clothing",
    "disguise",
    "distinctive_marks",
    "face",
    "hair",
    "injuries",
    "injury",
    "skin",
}

IDENTITY_PATHS = {
    "body.build",
    "body.height",
    "face.distinctive_mark",
    "face.eye_color",
    "face.shape",
    "skin.color",
}


@dataclass(frozen=True)
class AggregationObservation:
    id: UUID
    fingerprint: str
    field_path: str
    value: Any
    temporal_scope: dict[str, Any]
    source_kind: str
    epistemic_status: str
    grounding_status: str
    confidence: float


@dataclass(frozen=True)
class DerivedAppearanceState:
    fingerprint: str
    temporal_scope: dict[str, Any]
    label: str
    state_kind: str
    merge_priority: int
    age_stage: str | None
    appearance: dict[str, Any]
    field_sources: dict[str, list[str]]


@dataclass(frozen=True)
class DerivedConflict:
    field_path: str
    state_fingerprints: tuple[str, ...]
    candidate_values: tuple[Any, ...]
    temporal_scope: dict[str, Any]
    merge_priority: int


@dataclass(frozen=True)
class AppearanceAggregationResult:
    input_fingerprint: str
    identity_anchor: dict[str, Any]
    identity_sources: dict[str, list[str]]
    states: tuple[DerivedAppearanceState, ...]
    conflicts: tuple[DerivedConflict, ...]
    rejected_observation_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class _FieldAssignment:
    field_path: str
    value: Any
    source_ids: tuple[str, ...]
    scope: dict[str, Any]
    state_kind: str
    merge_priority: int
    conflict_key: str | None = None


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


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


def _allowed(field_path: str) -> bool:
    if not field_path or any(not part for part in field_path.split(".")):
        return False
    return field_path.split(".", 1)[0] in ALLOWED_VISUAL_ROOTS


def _state_kind(field_path: str, source_kind: str) -> tuple[str, int]:
    if source_kind == "manual":
        return "manual_override", 1_000
    root = field_path.split(".", 1)[0]
    if root in {"clothing", "accessory", "accessories"}:
        return "clothing", 30
    if root == "disguise":
        return "disguise", 40
    if root in {"cleanliness"}:
        return "temporary_condition", 50
    if root in {"injury", "injuries", "distinctive_marks"} or any(
        token in field_path for token in ("injury", "scar", "change")
    ):
        return "persistent_change", 20
    return "base_age_stage", 10


def _normalize_scope(scope: dict[str, Any], field_path: str) -> dict[str, Any]:
    normalized = {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in scope.items()
        if not key.startswith("_")
    }
    normalized.setdefault("scope_type", "unknown")
    normalized.setdefault("presentation_mode", "direct")
    normalized.setdefault("reality_status", "canonical")
    root = field_path.split(".", 1)[0]
    temporary = root in {"accessory", "accessories", "cleanliness", "clothing", "disguise"}
    if normalized["scope_type"] != "unknown":
        normalized["scope_type"] = "scene" if temporary else "persistent"
    if temporary:
        if normalized.get("start_chapter_ordinal") is not None:
            normalized.setdefault("end_chapter_ordinal", normalized["start_chapter_ordinal"])
        if normalized.get("start_event_id") is not None:
            normalized.setdefault("end_event_id", normalized["start_event_id"])
        if normalized.get("start_scene_order") is not None:
            normalized.setdefault("end_scene_order", normalized["start_scene_order"])
    return normalized


def _scope_domain(scope: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(scope.get("timeline_id", "")),
        str(scope.get("reality_status", "canonical")),
        str(scope.get("presentation_mode", "direct")),
    )


def _position(scope: dict[str, Any]) -> tuple[int, str] | None:
    chapter = scope.get("start_chapter_ordinal")
    if chapter is not None:
        return int(chapter), "chapter"
    scene = scope.get("start_scene_order")
    if scene is not None:
        return int(scene), "scene"
    return None


def _close_before(scope: dict[str, Any], next_scope: dict[str, Any]) -> dict[str, Any]:
    closed = dict(scope)
    current = _position(scope)
    following = _position(next_scope)
    if current is None or following is None or current[1] != following[1]:
        return closed
    if following[1] == "chapter":
        closed["end_chapter_ordinal"] = max(current[0], following[0] - 1)
    else:
        closed["end_scene_order"] = max(current[0], following[0] - 1)
    return closed


def _eligible(observation: AggregationObservation) -> bool:
    if not _allowed(observation.field_path):
        return False
    if observation.source_kind not in {"text", "manual"}:
        return False
    if observation.epistemic_status != "asserted":
        return False
    if observation.grounding_status not in {"exact", "manually_grounded"}:
        return False
    return observation.confidence >= 0.5


def _identity_values(
    observations: list[AggregationObservation],
) -> tuple[dict[str, Any], dict[str, list[str]], set[UUID]]:
    by_path: dict[str, list[AggregationObservation]] = {}
    for item in observations:
        if item.field_path in IDENTITY_PATHS:
            by_path.setdefault(item.field_path, []).append(item)
    anchor: dict[str, Any] = {}
    sources: dict[str, list[str]] = {}
    consumed: set[UUID] = set()
    for path, items in sorted(by_path.items()):
        canonical_values = {canonical_json(item.value) for item in items}
        domains = {_scope_domain(item.temporal_scope) for item in items}
        canonical_reality = all(domain[1:] == ("canonical", "direct") for domain in domains)
        if len(canonical_values) != 1 or not canonical_reality:
            continue
        value = min(items, key=lambda item: str(item.id)).value
        _put_path(anchor, path, value)
        sources[path] = sorted(str(item.id) for item in items)
        consumed.update(item.id for item in items)
    return anchor, sources, consumed


def _field_assignments(
    observations: list[AggregationObservation],
) -> list[_FieldAssignment]:
    grouped: dict[tuple[str, tuple[str, str, str]], list[AggregationObservation]] = {}
    for item in observations:
        grouped.setdefault((item.field_path, _scope_domain(item.temporal_scope)), []).append(item)

    assignments: list[_FieldAssignment] = []
    for (field_path, _), items in sorted(grouped.items(), key=lambda item: item[0]):
        positioned: dict[tuple[int, str] | None, list[AggregationObservation]] = {}
        for item in items:
            normalized_scope = _normalize_scope(item.temporal_scope, field_path)
            positioned.setdefault(_position(normalized_scope), []).append(item)
        ordered_positions = sorted(
            positioned,
            key=lambda value: (value is None, value or (0, "")),
        )
        for index, position in enumerate(ordered_positions):
            position_items = positioned[position]
            normalized_scope = _normalize_scope(position_items[0].temporal_scope, field_path)
            if index + 1 < len(ordered_positions):
                next_items = positioned[ordered_positions[index + 1]]
                normalized_scope = _close_before(
                    normalized_scope,
                    _normalize_scope(next_items[0].temporal_scope, field_path),
                )
            by_value: dict[str, list[AggregationObservation]] = {}
            for item in position_items:
                by_value.setdefault(canonical_json(item.value), []).append(item)
            conflict_key = (
                _hash({"field_path": field_path, "scope": normalized_scope})
                if len(by_value) > 1
                else None
            )
            for value_items in (by_value[key] for key in sorted(by_value)):
                representative = min(value_items, key=lambda item: str(item.id))
                kind, priority = _state_kind(field_path, representative.source_kind)
                assignments.append(
                    _FieldAssignment(
                        field_path=field_path,
                        value=representative.value,
                        source_ids=tuple(sorted(str(item.id) for item in value_items)),
                        scope=normalized_scope,
                        state_kind=kind,
                        merge_priority=priority,
                        conflict_key=conflict_key,
                    )
                )
    return assignments


def _state_label(scope: dict[str, Any], state_kind: str) -> str:
    chapter = scope.get("start_chapter_ordinal")
    if chapter is not None:
        return f"Chapter {chapter} · {state_kind}"
    return f"{scope.get('reality_status', 'canonical')} · {state_kind}"


def aggregate_appearance(
    *,
    character_id: UUID,
    source_document_version_id: UUID,
    observations: list[AggregationObservation],
    timeline_graph_version: str,
) -> AppearanceAggregationResult:
    eligible = sorted(
        (item for item in observations if _eligible(item)),
        key=lambda item: (item.field_path, canonical_json(item.temporal_scope), str(item.id)),
    )
    rejected = tuple(sorted((item.id for item in observations if item not in eligible), key=str))
    input_fingerprint = _hash(
        {
            "character_id": str(character_id),
            "source_document_version_id": str(source_document_version_id),
            "observation_fingerprints": sorted(item.fingerprint for item in eligible),
            "timeline_graph_version": timeline_graph_version,
            "reality_compatibility_version": REALITY_COMPATIBILITY_VERSION,
            "field_persistence_policy_version": FIELD_PERSISTENCE_POLICY_VERSION,
            "visual_schema_version": VISUAL_SCHEMA_VERSION,
            "resolver_version": RESOLVER_VERSION,
        }
    )
    identity_anchor, identity_sources, consumed = _identity_values(eligible)
    assignments = _field_assignments([item for item in eligible if item.id not in consumed])

    normal_groups: dict[tuple[str, str, int], list[_FieldAssignment]] = {}
    conflict_assignments: dict[str, list[_FieldAssignment]] = {}
    for assignment in assignments:
        if assignment.conflict_key is not None:
            conflict_assignments.setdefault(assignment.conflict_key, []).append(assignment)
            continue
        group_key = (
            canonical_json(assignment.scope),
            assignment.state_kind,
            assignment.merge_priority,
        )
        normal_groups.setdefault(group_key, []).append(assignment)

    state_payloads: list[tuple[dict[str, Any], str, int, list[_FieldAssignment]]] = []
    for (_, kind, priority), items in sorted(normal_groups.items()):
        state_payloads.append((items[0].scope, kind, priority, items))
    for items in conflict_assignments.values():
        for item in items:
            state_payloads.append((item.scope, item.state_kind, item.merge_priority, [item]))

    states: list[DerivedAppearanceState] = []
    assignment_state: dict[tuple[str, str], str] = {}
    for scope, kind, priority, items in sorted(
        state_payloads,
        key=lambda item: (canonical_json(item[0]), item[1], item[2], item[3][0].field_path),
    ):
        appearance: dict[str, Any] = {}
        field_sources: dict[str, list[str]] = {}
        for item in sorted(items, key=lambda value: value.field_path):
            _put_path(appearance, item.field_path, item.value)
            field_sources[item.field_path] = list(item.source_ids)
        age_value = appearance.get("age_stage")
        if age_value is None and isinstance(appearance.get("age"), dict):
            age_value = appearance["age"].get("stage")
        age_stage = str(age_value) if age_value is not None else None
        fingerprint = _hash(
            {
                "character_id": str(character_id),
                "scope": scope,
                "state_kind": kind,
                "merge_priority": priority,
                "appearance": appearance,
                "field_sources": field_sources,
                "resolver_version": RESOLVER_VERSION,
            }
        )
        states.append(
            DerivedAppearanceState(
                fingerprint=fingerprint,
                temporal_scope=scope,
                label=_state_label(scope, kind),
                state_kind=kind,
                merge_priority=priority,
                age_stage=age_stage,
                appearance=appearance,
                field_sources=field_sources,
            )
        )
        for item in items:
            assignment_state[(item.conflict_key or "", canonical_json(item.value))] = fingerprint

    conflicts: list[DerivedConflict] = []
    for conflict_key, items in sorted(conflict_assignments.items()):
        state_fingerprints = tuple(
            assignment_state[(conflict_key, canonical_json(item.value))]
            for item in sorted(items, key=lambda value: canonical_json(value.value))
        )
        conflicts.append(
            DerivedConflict(
                field_path=items[0].field_path,
                state_fingerprints=state_fingerprints,
                candidate_values=tuple(
                    item.value
                    for item in sorted(items, key=lambda value: canonical_json(value.value))
                ),
                temporal_scope=items[0].scope,
                merge_priority=max(item.merge_priority for item in items),
            )
        )
    return AppearanceAggregationResult(
        input_fingerprint=input_fingerprint,
        identity_anchor=identity_anchor,
        identity_sources=identity_sources,
        states=tuple(states),
        conflicts=tuple(conflicts),
        rejected_observation_ids=rejected,
    )
