from __future__ import annotations

import json
import unicodedata
from hashlib import sha256
from itertools import combinations
from typing import Mapping, Sequence

from .appearance_state_segments import PERSISTENCE_VALUES
from .errors import ContractValidationError
from .text import SourceSpan

APPEARANCE_RELATION_POLICY_VERSION = "same-segment-exact-attribute-relations-v1"
APPEARANCE_PROPOSITION_POLICY_VERSION = "equivalent-components-representative-v1"
RELATION_TYPES = (
    "equivalent",
    "compatible",
    "temporal_change",
    "state_change",
    "true_conflict",
    "unclassified",
)
RELATION_DIRECTIONS = (
    "symmetric",
    "left_contains_right",
    "right_contains_left",
    "earlier_to_later",
    "unknown",
)
RELATION_RULES = (
    "exact_value",
    "value_containment",
    "no_safe_deterministic_rule",
)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} must be a non-empty string")
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


def _comparison_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if not character.isspace()
    )


def _classify_pair(
    left_value: str,
    right_value: str,
) -> tuple[str, str, str]:
    left = _comparison_text(left_value)
    right = _comparison_text(right_value)
    if left == right:
        return "equivalent", "symmetric", "exact_value"
    if min(len(left), len(right)) >= 2:
        if right in left:
            return "compatible", "left_contains_right", "value_containment"
        if left in right:
            return "compatible", "right_contains_left", "value_containment"
    return "unclassified", "unknown", "no_safe_deterministic_rule"


def _fact_sort_key(fact: Mapping[str, object]) -> tuple[int, int, str]:
    span = _span(fact.get("document_fact_span"), "canonical_fact.document_fact_span")
    return span.start, span.end, str(fact["canonical_fact_id"])


class _DisjointSet:
    def __init__(self, members: Sequence[str]) -> None:
        self._parent = {member: member for member in members}

    def find(self, member: str) -> str:
        parent = self._parent[member]
        if parent != member:
            self._parent[member] = self.find(parent)
        return self._parent[member]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            self._parent[right_root] = left_root
        else:
            self._parent[left_root] = right_root


def build_appearance_semantic_projection(
    *,
    source_document_version_id: str,
    document_length: int,
    fact_groups: Mapping[str, object],
    fact_assignments: Sequence[Mapping[str, object]],
    state_segments: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build relations first, then propositions from equivalent components only."""
    source_document_version_id = _string(
        source_document_version_id, "source_document_version_id"
    )
    if isinstance(document_length, bool) or not isinstance(document_length, int):
        raise ContractValidationError("document_length must be an integer")
    if document_length <= 0:
        raise ContractValidationError("document_length must be positive")
    if fact_groups.get("source_document_version_id") not in {
        None,
        source_document_version_id,
    }:
        raise ContractValidationError("fact groups refer to a different source document")

    roster_present = "characters" in fact_groups
    character_ids: list[str] = []
    expected_fact_ids_by_character: dict[str, set[str]] = {}
    if roster_present:
        for index, raw_character in enumerate(
            _sequence(fact_groups.get("characters"), "fact_groups.characters")
        ):
            character = _mapping(raw_character, f"fact_groups.characters[{index}]")
            character_id = _string(
                character.get("character_id"),
                f"fact_groups.characters[{index}].character_id",
            )
            if character_id in expected_fact_ids_by_character:
                raise ContractValidationError("duplicate character in fact group roster")
            raw_fact_ids = character.get("canonical_fact_ids", [])
            fact_ids = {
                _string(fact_id, f"fact_groups.characters[{index}].canonical_fact_ids")
                for fact_id in _sequence(
                    raw_fact_ids,
                    f"fact_groups.characters[{index}].canonical_fact_ids",
                )
            }
            if len(fact_ids) != len(raw_fact_ids):
                raise ContractValidationError("duplicate fact reference in character roster")
            character_ids.append(character_id)
            expected_fact_ids_by_character[character_id] = fact_ids

    facts: dict[str, Mapping[str, object]] = {}
    actual_fact_ids_by_character: dict[str, set[str]] = {
        character_id: set() for character_id in character_ids
    }
    for index, raw_fact in enumerate(
        _sequence(fact_groups.get("fact_groups"), "fact_groups.fact_groups")
    ):
        fact = _mapping(raw_fact, f"fact_groups.fact_groups[{index}]")
        canonical_fact_id = _string(
            fact.get("canonical_fact_id"),
            f"fact_groups.fact_groups[{index}].canonical_fact_id",
        )
        if canonical_fact_id in facts:
            raise ContractValidationError("duplicate canonical fact id")
        character_id = _string(
            fact.get("character_id"),
            f"fact_groups.fact_groups[{index}].character_id",
        )
        if roster_present and character_id not in expected_fact_ids_by_character:
            raise ContractValidationError("canonical fact references unknown character")
        if not roster_present and character_id not in actual_fact_ids_by_character:
            character_ids.append(character_id)
            actual_fact_ids_by_character[character_id] = set()
        _string(fact.get("category"), f"fact_groups.fact_groups[{index}].category")
        _string(fact.get("attribute"), f"fact_groups.fact_groups[{index}].attribute")
        _string(fact.get("value"), f"fact_groups.fact_groups[{index}].value")
        span = _span(
            fact.get("document_fact_span"),
            f"fact_groups.fact_groups[{index}].document_fact_span",
        )
        if span.end > document_length:
            raise ContractValidationError("canonical fact span exceeds document")
        facts[canonical_fact_id] = fact
        actual_fact_ids_by_character[character_id].add(canonical_fact_id)
    if roster_present and expected_fact_ids_by_character != actual_fact_ids_by_character:
        raise ContractValidationError("character roster and canonical fact ownership differ")

    assignments: dict[str, Mapping[str, object]] = {}
    for index, raw_assignment in enumerate(fact_assignments):
        assignment = _mapping(raw_assignment, f"fact_assignments[{index}]")
        canonical_fact_id = _string(
            assignment.get("canonical_fact_id"),
            f"fact_assignments[{index}].canonical_fact_id",
        )
        if canonical_fact_id in assignments:
            raise ContractValidationError("duplicate fact assignment canonical fact id")
        fact = facts.get(canonical_fact_id)
        if fact is None:
            raise ContractValidationError("fact assignment references unknown canonical fact")
        if assignment.get("character_id") != fact.get("character_id"):
            raise ContractValidationError("fact assignment character does not match canonical fact")
        persistence = _string(
            assignment.get("persistence"), f"fact_assignments[{index}].persistence"
        )
        if persistence not in PERSISTENCE_VALUES:
            raise ContractValidationError("fact assignment has unsupported persistence")
        for dimension in ("life", "form", "scene"):
            _string(assignment.get(dimension), f"fact_assignments[{index}].{dimension}")
        assignments[canonical_fact_id] = assignment
    if set(assignments) != set(facts):
        raise ContractValidationError("fact assignments and canonical fact groups differ")

    segment_by_id: dict[str, Mapping[str, object]] = {}
    segments_by_character: dict[str, list[Mapping[str, object]]] = {
        character_id: [] for character_id in character_ids
    }
    fact_to_segment: dict[str, str] = {}
    for index, raw_segment in enumerate(state_segments):
        segment = _mapping(raw_segment, f"state_segments[{index}]")
        segment_id = _string(
            segment.get("state_segment_id"), f"state_segments[{index}].state_segment_id"
        )
        if segment_id in segment_by_id:
            raise ContractValidationError("duplicate state_segment_id")
        character_id = _string(
            segment.get("character_id"), f"state_segments[{index}].character_id"
        )
        if character_id not in segments_by_character:
            raise ContractValidationError("state segment references unknown character")
        _integer(segment.get("sequence_index"), f"state_segments[{index}].sequence_index")
        segment_span = _span(
            segment.get("document_span"), f"state_segments[{index}].document_span"
        )
        if segment_span.end > document_length:
            raise ContractValidationError("state segment exceeds document")
        for dimension in ("life", "form", "scene"):
            _string(segment.get(dimension), f"state_segments[{index}].{dimension}")
        for fact_id_value in _sequence(
            segment.get("observed_fact_ids"), f"state_segments[{index}].observed_fact_ids"
        ):
            canonical_fact_id = _string(
                fact_id_value, f"state_segments[{index}].observed_fact_ids"
            )
            if canonical_fact_id in fact_to_segment:
                raise ContractValidationError("canonical fact is observed by multiple segments")
            fact = facts.get(canonical_fact_id)
            if fact is None:
                raise ContractValidationError("state segment observes unknown canonical fact")
            if fact.get("character_id") != character_id:
                raise ContractValidationError("observed fact character does not match segment")
            fact_span = _span(
                fact.get("document_fact_span"), "canonical_fact.document_fact_span"
            )
            if not segment_span.start <= fact_span.start < segment_span.end:
                raise ContractValidationError("observed fact starts outside state segment")
            assignment = assignments[canonical_fact_id]
            if any(assignment[dimension] != segment[dimension] for dimension in ("life", "form", "scene")):
                raise ContractValidationError("fact assignment state does not match state segment")
            fact_to_segment[canonical_fact_id] = segment_id
        segment_by_id[segment_id] = segment
        segments_by_character[character_id].append(segment)
    if set(fact_to_segment) != set(facts):
        raise ContractValidationError("every canonical fact must be observed by one state segment")

    for character_id, segments in segments_by_character.items():
        if not segments:
            raise ContractValidationError("every character must have at least one state segment")
        segments.sort(key=lambda item: int(item["sequence_index"]))
        if [int(item["sequence_index"]) for item in segments] != list(range(len(segments))):
            raise ContractValidationError("state segment sequence indexes must be contiguous")
        spans = [_span(item["document_span"], "state_segment.document_span") for item in segments]
        if spans[0].start != 0 or spans[-1].end != document_length:
            raise ContractValidationError("character state segments must cover the document")
        if any(left.end != right.start for left, right in zip(spans, spans[1:])):
            raise ContractValidationError("character state segments must be contiguous")

    group_items: dict[tuple[str, str, str], list[Mapping[str, object]]] = {}
    for canonical_fact_id, fact in facts.items():
        key = (
            str(fact["character_id"]),
            fact_to_segment[canonical_fact_id],
            str(fact["attribute"]),
        )
        group_items.setdefault(key, []).append(fact)

    relations: list[dict[str, object]] = []
    equivalent_pairs: set[tuple[str, str]] = set()
    for (character_id, segment_id, attribute), group in sorted(group_items.items()):
        ordered = sorted(group, key=_fact_sort_key)
        for left, right in combinations(ordered, 2):
            relation, direction, rule = _classify_pair(str(left["value"]), str(right["value"]))
            left_fact_id = str(left["canonical_fact_id"])
            right_fact_id = str(right["canonical_fact_id"])
            relation_payload = {
                "source_document_version_id": source_document_version_id,
                "relation_policy_version": APPEARANCE_RELATION_POLICY_VERSION,
                "character_id": character_id,
                "state_segment_id": segment_id,
                "attribute": attribute,
                "left_fact_id": left_fact_id,
                "right_fact_id": right_fact_id,
                "relation": relation,
                "direction": direction,
                "rule": rule,
            }
            relations.append(
                {
                    "relation_id": _stable_id("relation", relation_payload),
                    **{
                        key: value
                        for key, value in relation_payload.items()
                        if key not in {"source_document_version_id", "relation_policy_version"}
                    },
                }
            )
            if relation == "equivalent":
                equivalent_pairs.add((left_fact_id, right_fact_id))

    propositions: list[dict[str, object]] = []
    for (character_id, segment_id, attribute), group in sorted(group_items.items()):
        ordered = sorted(group, key=_fact_sort_key)
        member_ids = [str(fact["canonical_fact_id"]) for fact in ordered]
        components = _DisjointSet(member_ids)
        for left_fact_id, right_fact_id in equivalent_pairs:
            if left_fact_id in member_ids and right_fact_id in member_ids:
                components.union(left_fact_id, right_fact_id)
        component_members: dict[str, list[Mapping[str, object]]] = {}
        for fact in ordered:
            fact_id = str(fact["canonical_fact_id"])
            component_members.setdefault(components.find(fact_id), []).append(fact)
        for members in component_members.values():
            members.sort(key=_fact_sort_key)
            representative = members[0]
            proposition_member_ids = [str(item["canonical_fact_id"]) for item in members]
            source_values = list(dict.fromkeys(str(item["value"]) for item in members))
            categories = sorted({str(item["category"]) for item in members})
            proposition_payload = {
                "source_document_version_id": source_document_version_id,
                "normalization_policy_version": APPEARANCE_PROPOSITION_POLICY_VERSION,
                "character_id": character_id,
                "state_segment_id": segment_id,
                "attribute": attribute,
                "member_fact_ids": proposition_member_ids,
            }
            propositions.append(
                {
                    "proposition_id": _stable_id("proposition", proposition_payload),
                    "character_id": character_id,
                    "state_segment_id": segment_id,
                    "attribute": attribute,
                    "normalized_value": str(representative["value"]),
                    "categories": categories,
                    "representative_fact_id": str(representative["canonical_fact_id"]),
                    "member_fact_ids": proposition_member_ids,
                    "source_values": source_values,
                    "normalization_basis": (
                        "equivalent_component" if len(members) > 1 else "singleton"
                    ),
                }
            )
    propositions.sort(
        key=lambda item: (
            str(item["character_id"]),
            _span(segment_by_id[str(item["state_segment_id"])]["document_span"], "segment").start,
            _fact_sort_key(facts[str(item["representative_fact_id"])]),
            str(item["proposition_id"]),
        )
    )
    proposition_fact_ids = [
        fact_id
        for proposition in propositions
        for fact_id in proposition["member_fact_ids"]
    ]
    if len(proposition_fact_ids) != len(set(proposition_fact_ids)) or set(proposition_fact_ids) != set(facts):
        raise ContractValidationError("every canonical fact must belong to one proposition")

    counts = {
        relation_type: sum(item["relation"] == relation_type for item in relations)
        for relation_type in RELATION_TYPES
    }
    return {
        "relation_policy_version": APPEARANCE_RELATION_POLICY_VERSION,
        "normalization_policy_version": APPEARANCE_PROPOSITION_POLICY_VERSION,
        "relations": relations,
        "normalized_propositions": propositions,
        "summary": {
            "relation_candidates": len(relations),
            "equivalent_relations": counts["equivalent"],
            "compatible_relations": counts["compatible"],
            "temporal_change_relations": counts["temporal_change"],
            "state_change_relations": counts["state_change"],
            "true_conflict_relations": counts["true_conflict"],
            "unclassified_relations": counts["unclassified"],
            "normalized_propositions": len(propositions),
            "semantic_model_calls": 0,
        },
    }
