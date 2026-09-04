from __future__ import annotations

import json
from hashlib import sha256
from typing import Mapping, Sequence

from .errors import ContractValidationError
from .text import SourceSpan, find_safe_quote_matches

STATE_SEGMENT_POLICY_VERSION = "transition-boundary-observation-v1"
TRANSITION_DIMENSION_ORDER = {"life": 0, "form": 1, "scene": 2, "appearance": 3}
STATE_ATTRIBUTE_BY_DIMENSION = {
    "life": "life_stage",
    "form": "form_state",
    "scene": "scene_state",
}
BOUNDARY_REASON_ORDER = {
    "document_start": 0,
    "transition": 1,
    "scene_expiry": 2,
    "document_end": 3,
}
PERSISTENCE_VALUES = {
    "stable",
    "persistent_until_changed",
    "scene",
    "momentary",
    "unknown",
}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _string(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        requirement = "a string" if allow_empty else "a non-empty string"
        raise ContractValidationError(f"{label} must be {requirement}")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractValidationError(f"{label} must be an integer")
    return value


def _span(value: object, label: str) -> SourceSpan:
    item = _mapping(value, label)
    if set(item) != {"start", "end"}:
        raise ContractValidationError(f"{label} must contain only start/end")
    return SourceSpan(
        _integer(item.get("start"), f"{label}.start"),
        _integer(item.get("end"), f"{label}.end"),
    )


def _stable_id(prefix: str, payload: Mapping[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{prefix}-{sha256(serialized.encode('utf-8')).hexdigest()[:20]}"


def attach_transition_ids(
    *,
    document_text: str,
    source_document_version_id: str,
    transition_policy_version: str,
    transitions: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Validate final grounded transitions and attach content-derived stable IDs."""
    if not document_text:
        raise ContractValidationError("state segments require non-empty document text")
    source_document_version_id = _string(
        source_document_version_id, "source_document_version_id"
    )
    transition_policy_version = _string(
        transition_policy_version, "transition_policy_version"
    )
    identified: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, raw_transition in enumerate(transitions):
        transition = _mapping(raw_transition, f"transitions[{index}]")
        allowed_fields = {
            "transition_id",
            "character_id",
            "evidence",
            "document_span",
            "dimension",
            "attribute",
            "before",
            "after",
            "change",
        }
        if not set(transition).issubset(allowed_fields):
            raise ContractValidationError("grounded transition has unsupported fields")
        character_id = _string(
            transition.get("character_id"), f"transitions[{index}].character_id"
        )
        evidence = _string(transition.get("evidence"), f"transitions[{index}].evidence")
        span = _span(
            transition.get("document_span"), f"transitions[{index}].document_span"
        )
        if span.quote(document_text) != evidence:
            raise ContractValidationError("transition evidence does not replay from source text")
        dimension = _string(
            transition.get("dimension"), f"transitions[{index}].dimension"
        )
        if dimension not in TRANSITION_DIMENSION_ORDER:
            raise ContractValidationError("transition has unsupported dimension")
        attribute = _string(
            transition.get("attribute"), f"transitions[{index}].attribute"
        )
        expected_attribute = STATE_ATTRIBUTE_BY_DIMENSION.get(dimension)
        if expected_attribute is not None and attribute != expected_attribute:
            raise ContractValidationError("transition attribute does not match dimension")
        before = _string(
            transition.get("before"),
            f"transitions[{index}].before",
            allow_empty=True,
        )
        after = _string(
            transition.get("after"),
            f"transitions[{index}].after",
            allow_empty=True,
        )
        if not before and not after:
            raise ContractValidationError("transition before/after cannot both be empty")
        if before and before == after:
            raise ContractValidationError("transition before/after cannot be equal")
        before_matches = find_safe_quote_matches(evidence, before) if before else ()
        after_matches = find_safe_quote_matches(evidence, after) if after else ()
        if before and len(before_matches) != 1:
            raise ContractValidationError("transition before state is not uniquely grounded")
        if after and len(after_matches) != 1:
            raise ContractValidationError("transition after state is not uniquely grounded")
        if before and after and before_matches[0].span.end > after_matches[0].span.start:
            raise ContractValidationError("transition states are not grounded in source order")
        change = _string(transition.get("change"), f"transitions[{index}].change")
        expected_change = "change" if before and after else ("enter" if after else "exit")
        if change != expected_change:
            raise ContractValidationError("transition change does not match before/after")
        base: dict[str, object] = {
            "character_id": character_id,
            "evidence": evidence,
            "document_span": span.to_dict(),
            "dimension": dimension,
            "attribute": attribute,
            "before": before,
            "after": after,
            "change": change,
        }
        transition_id = _stable_id(
            "transition",
            {
                "source_document_version_id": source_document_version_id,
                "transition_policy_version": transition_policy_version,
                **base,
            },
        )
        supplied_id = transition.get("transition_id")
        if supplied_id is not None and supplied_id != transition_id:
            raise ContractValidationError("transition_id does not match grounded transition")
        if transition_id in seen_ids:
            raise ContractValidationError("duplicate grounded transition")
        seen_ids.add(transition_id)
        identified.append({"transition_id": transition_id, **base})
    return tuple(identified)


def transition_effective_position(transition: Mapping[str, object]) -> int:
    span = _span(transition.get("document_span"), "transition.document_span")
    after = _string(transition.get("after"), "transition.after", allow_empty=True)
    if not after:
        return span.end
    evidence = _string(transition.get("evidence"), "transition.evidence")
    matches = find_safe_quote_matches(evidence, after)
    if len(matches) != 1:
        raise ContractValidationError("transition after state is not uniquely grounded in evidence")
    return span.start + matches[0].span.start


def scene_expiry_position(
    *,
    document_text: str,
    transition: Mapping[str, object],
    chapter_spans: Sequence[SourceSpan],
) -> int:
    span = _span(transition.get("document_span"), "transition.document_span")
    newline = document_text.find("\n", span.end)
    line_end = len(document_text) if newline < 0 else newline
    chapter_end = next(
        (chapter.end for chapter in chapter_spans if chapter.start <= span.start < chapter.end),
        None,
    )
    if chapter_end is None:
        raise ContractValidationError("transition does not belong to a chapter span")
    return min(line_end, chapter_end)


def _boundary(
    position: int,
    reasons: set[str],
    transition_ids: set[str],
) -> dict[str, object]:
    return {
        "position": position,
        "reasons": sorted(reasons, key=BOUNDARY_REASON_ORDER.__getitem__),
        "transition_ids": sorted(transition_ids),
    }


def build_character_state_segments(
    *,
    document_text: str,
    source_document_version_id: str,
    chapters: Sequence[Mapping[str, object]],
    fact_groups: Mapping[str, object],
    fact_assignments: Sequence[Mapping[str, object]],
    transitions: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Build a complete, deterministic StateSegment partition for every character."""
    if not document_text:
        raise ContractValidationError("state segments require non-empty document text")
    source_document_version_id = _string(
        source_document_version_id, "source_document_version_id"
    )
    chapter_spans = tuple(
        _span(_mapping(chapter, "chapter").get("document_span"), "chapter.document_span")
        for chapter in chapters
    )
    if not chapter_spans:
        raise ContractValidationError("state segments require chapter spans")
    if chapter_spans[0].start != 0 or chapter_spans[-1].end != len(document_text):
        raise ContractValidationError("chapter spans must cover the complete document")
    for previous, following in zip(chapter_spans, chapter_spans[1:]):
        if previous.end != following.start:
            raise ContractValidationError("chapter spans must be contiguous")

    roster_present = "characters" in fact_groups
    character_ids: list[str] = []
    seen_character_ids: set[str] = set()
    if roster_present:
        for index, raw_character in enumerate(
            _sequence(fact_groups.get("characters"), "fact_groups.characters")
        ):
            character = _mapping(raw_character, f"fact_groups.characters[{index}]")
            character_id = _string(
                character.get("character_id"),
                f"fact_groups.characters[{index}].character_id",
            )
            if character_id in seen_character_ids:
                raise ContractValidationError("duplicate character in fact group roster")
            seen_character_ids.add(character_id)
            character_ids.append(character_id)

    groups: dict[str, tuple[str, SourceSpan]] = {}
    for index, raw_group in enumerate(
        _sequence(fact_groups.get("fact_groups"), "fact_groups.fact_groups")
    ):
        group = _mapping(raw_group, f"fact_groups.fact_groups[{index}]")
        canonical_fact_id = _string(
            group.get("canonical_fact_id"),
            f"fact_groups.fact_groups[{index}].canonical_fact_id",
        )
        if canonical_fact_id in groups:
            raise ContractValidationError("duplicate canonical fact id")
        character_id = _string(
            group.get("character_id"),
            f"fact_groups.fact_groups[{index}].character_id",
        )
        if roster_present and character_id not in seen_character_ids:
            raise ContractValidationError("canonical fact references unknown character")
        if not roster_present and character_id not in seen_character_ids:
            seen_character_ids.add(character_id)
            character_ids.append(character_id)
        fact_span = _span(
            group.get("document_fact_span"),
            f"fact_groups.fact_groups[{index}].document_fact_span",
        )
        fact_span.validate_container(document_text)
        fact_quote = group.get("fact_quote")
        if fact_quote is not None and fact_span.quote(document_text) != _string(
            fact_quote, f"fact_groups.fact_groups[{index}].fact_quote"
        ):
            raise ContractValidationError("canonical fact does not replay from source text")
        groups[canonical_fact_id] = (character_id, fact_span)

    assigned: dict[str, Mapping[str, object]] = {}
    facts_by_character: dict[str, list[tuple[int, str]]] = {
        character_id: [] for character_id in character_ids
    }
    for index, raw_assignment in enumerate(fact_assignments):
        assignment = _mapping(raw_assignment, f"fact_assignments[{index}]")
        canonical_fact_id = _string(
            assignment.get("canonical_fact_id"),
            f"fact_assignments[{index}].canonical_fact_id",
        )
        if canonical_fact_id in assigned:
            raise ContractValidationError("duplicate fact assignment canonical fact id")
        group = groups.get(canonical_fact_id)
        if group is None:
            raise ContractValidationError("fact assignment references unknown canonical fact")
        character_id = _string(
            assignment.get("character_id"), f"fact_assignments[{index}].character_id"
        )
        if character_id != group[0]:
            raise ContractValidationError("fact assignment character does not match canonical fact")
        persistence = _string(
            assignment.get("persistence"), f"fact_assignments[{index}].persistence"
        )
        if persistence not in PERSISTENCE_VALUES:
            raise ContractValidationError("fact assignment has unsupported persistence")
        assigned[canonical_fact_id] = assignment
        facts_by_character[character_id].append((group[1].start, canonical_fact_id))
    if set(assigned) != set(groups):
        raise ContractValidationError("fact assignments and canonical fact groups differ")
    for facts in facts_by_character.values():
        facts.sort(key=lambda item: (item[0], item[1]))

    transitions_by_character: dict[str, list[Mapping[str, object]]] = {
        character_id: [] for character_id in character_ids
    }
    seen_transition_ids: set[str] = set()
    for index, raw_transition in enumerate(transitions):
        transition = _mapping(raw_transition, f"transitions[{index}]")
        transition_id = _string(
            transition.get("transition_id"), f"transitions[{index}].transition_id"
        )
        if transition_id in seen_transition_ids:
            raise ContractValidationError("duplicate transition_id")
        seen_transition_ids.add(transition_id)
        character_id = _string(
            transition.get("character_id"), f"transitions[{index}].character_id"
        )
        if character_id not in transitions_by_character:
            raise ContractValidationError("transition references unknown character")
        position = transition_effective_position(transition)
        if not 0 <= position <= len(document_text):
            raise ContractValidationError("transition boundary falls outside document")
        transitions_by_character[character_id].append(transition)

    segments: list[dict[str, object]] = []
    for character_id in character_ids:
        boundary_reasons: dict[int, set[str]] = {
            0: {"document_start"},
            len(document_text): {"document_end"},
        }
        boundary_transition_ids: dict[int, set[str]] = {0: set(), len(document_text): set()}
        transitions_at: dict[int, list[Mapping[str, object]]] = {}
        expiries_at: dict[int, list[str]] = {}
        for transition in transitions_by_character[character_id]:
            transition_id = str(transition["transition_id"])
            position = transition_effective_position(transition)
            boundary_reasons.setdefault(position, set()).add("transition")
            boundary_transition_ids.setdefault(position, set()).add(transition_id)
            transitions_at.setdefault(position, []).append(transition)
            if transition["dimension"] == "scene" and transition["after"]:
                expiry = scene_expiry_position(
                    document_text=document_text,
                    transition=transition,
                    chapter_spans=chapter_spans,
                )
                if expiry > position:
                    boundary_reasons.setdefault(expiry, set()).add("scene_expiry")
                    boundary_transition_ids.setdefault(expiry, set()).add(transition_id)
                    expiries_at.setdefault(expiry, []).append(transition_id)

        positions = sorted(boundary_reasons)
        state = {"life": "unknown", "form": "unknown", "scene": "unknown"}
        scene_source_transition_id: str | None = None
        previous_position = 0
        sequence_index = 0
        for position in positions:
            if position > previous_position:
                observed_fact_ids = [
                    canonical_fact_id
                    for fact_position, canonical_fact_id in facts_by_character[character_id]
                    if previous_position <= fact_position < position
                ]
                start_boundary = _boundary(
                    previous_position,
                    boundary_reasons[previous_position],
                    boundary_transition_ids.setdefault(previous_position, set()),
                )
                end_boundary = _boundary(
                    position,
                    boundary_reasons[position],
                    boundary_transition_ids.setdefault(position, set()),
                )
                segment_payload: dict[str, object] = {
                    "source_document_version_id": source_document_version_id,
                    "state_segment_policy_version": STATE_SEGMENT_POLICY_VERSION,
                    "character_id": character_id,
                    "sequence_index": sequence_index,
                    "document_span": {"start": previous_position, "end": position},
                    "life": state["life"],
                    "form": state["form"],
                    "scene": state["scene"],
                }
                segments.append(
                    {
                        "state_segment_id": _stable_id("state", segment_payload),
                        "character_id": character_id,
                        "sequence_index": sequence_index,
                        "document_span": segment_payload["document_span"],
                        "life": state["life"],
                        "form": state["form"],
                        "scene": state["scene"],
                        "start_boundary": start_boundary,
                        "end_boundary": end_boundary,
                        "observed_fact_ids": observed_fact_ids,
                    }
                )
                sequence_index += 1
                previous_position = position

            for expiring_transition_id in sorted(expiries_at.get(position, [])):
                if scene_source_transition_id == expiring_transition_id:
                    state["scene"] = "unknown"
                    scene_source_transition_id = None
            for transition in sorted(
                transitions_at.get(position, []),
                key=lambda item: (
                    TRANSITION_DIMENSION_ORDER[str(item["dimension"])],
                    str(item["transition_id"]),
                ),
            ):
                dimension = str(transition["dimension"])
                after = str(transition["after"]) or "unknown"
                if dimension == "life":
                    state["life"] = after
                    state["form"] = "unknown"
                    state["scene"] = "unknown"
                    scene_source_transition_id = None
                elif dimension == "form":
                    state["form"] = after
                elif dimension == "scene":
                    state["scene"] = after
                    scene_source_transition_id = (
                        str(transition["transition_id"]) if after != "unknown" else None
                    )

    observed_ids = [
        canonical_fact_id
        for segment in segments
        for canonical_fact_id in segment["observed_fact_ids"]
    ]
    if len(observed_ids) != len(set(observed_ids)) or set(observed_ids) != set(groups):
        raise ContractValidationError("canonical facts must be observed by exactly one state segment")
    return tuple(segments)
