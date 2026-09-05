from __future__ import annotations

import copy
import json
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

from .fact_applicability import (
    FACT_APPLICABILITY_POLICY_VERSION, evaluate_fact_applicability,
    select_state_segments, validate_applicability_events,
)
from .appearance_scope import parse_document_chapters
from .appearance_semantic_relations import (
    APPEARANCE_PROPOSITION_POLICY_VERSION,
    APPEARANCE_RELATION_POLICY_VERSION,
    build_appearance_semantic_projection,
)
from .appearance_state_segments import (
    PERSISTENCE_VALUES,
    STATE_SEGMENT_POLICY_VERSION,
    attach_transition_ids,
    build_character_state_segments,
    transition_effective_position,
)
from .appearance_transition import (
    APPEARANCE_TRANSITION_POLICY_VERSION,
    DOCUMENT_APPEARANCE_STATES_VERSION,
)
from .errors import ContractValidationError
from .fact_groups import (
    DOCUMENT_CHARACTER_FACT_GROUPS_VERSION,
    POST_LINK_FACT_GROUPING_POLICY_VERSION,
)
from .label_review_projection import (
    DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION,
    LABEL_KINDS,
    LABEL_PROJECTION_POLICY_VERSION,
    LABEL_STABILITIES,
    REVIEW_PROJECTION_POLICY_VERSION,
    SOURCE_LABEL_ROLES,
)
from .text import SourceSpan, sha256_text


RENDER_PROFILE_REQUESTS_VERSION = "render-profile-compile-requests-v1"
RENDER_READY_CHARACTER_PROFILES_VERSION = "render-ready-character-profiles-v1"
RENDER_PROFILE_COMPILER_POLICY_VERSION = "snapshot-render-adapter-v2"
CHARACTER_SNAPSHOT_VERSION = "character-snapshot-v1"
CHARACTER_SNAPSHOT_POLICY_VERSION = "automatic-semantic-snapshot-v2"

PROFILE_STATUSES = (
    "compiled",
    "compiled_with_warnings",
    "selector_required",
    "no_matching_state",
)
APPLICABILITY_STATUSES = ("active", "provisional")
WARNING_CODES = (
    "selector_missing_document_position",
    "selector_ambiguous",
    "selector_no_match",
    "unknown_life_state",
    "unknown_form_state",
    "unknown_scene_state",
    "provisional_fact_applicability",
    "active_unclassified_relation",
    "provisional_unclassified_relation",
    "provisional_true_conflict_overlap",
    "actionable_identity_review",
    "provisional_incompatible_relation",
    "automatic_semantic_review",
)

_SELECTOR_FIELDS = {
    "life_stage": "life",
    "form_state": "form",
    "scene_state": "scene",
}
_PERSISTENCE_ORDER = {
    "stable": 0,
    "persistent_until_changed": 1,
    "scene": 2,
    "momentary": 3,
    "unknown": 4,
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


def _hex_string(value: object, label: str, *, length: int = 64) -> str:
    text = _string(value, label)
    if len(text) != length or any(character not in "0123456789abcdef" for character in text):
        raise ContractValidationError(f"{label} must be {length} lowercase hex characters")
    return text


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_hash(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_unordered(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _normalize_unordered(member) for key, member in value.items()}
    if isinstance(value, list):
        members = [_normalize_unordered(member) for member in value]
        return sorted(members, key=_canonical_json)
    return value


def _order_independent_hash(value: object) -> str:
    return _canonical_hash(_normalize_unordered(value))


def _stable_id(prefix: str, payload: Mapping[str, object]) -> str:
    return f"{prefix}-{_canonical_hash(payload)[:20]}"


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"cannot read valid JSON from {path}") from exc


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _warning(code: str, message: str, related_ids: Sequence[str] = ()) -> dict[str, object]:
    if code not in WARNING_CODES:
        raise ContractValidationError("unsupported compile warning code")
    return {
        "code": code,
        "message": message,
        "related_ids": sorted(set(related_ids)),
    }


def _validate_fact_provenance(
    *,
    document_text: str,
    fact: Mapping[str, object],
    label: str,
) -> dict[str, object]:
    fact_id = _string(fact.get("canonical_fact_id"), f"{label}.canonical_fact_id")
    character_id = _string(fact.get("character_id"), f"{label}.character_id")
    fact_quote = _string(fact.get("fact_quote"), f"{label}.fact_quote")
    category = _string(fact.get("category"), f"{label}.category")
    attribute = _string(fact.get("attribute"), f"{label}.attribute")
    value = _string(fact.get("value"), f"{label}.value")
    fact_span = _span(fact.get("document_fact_span"), f"{label}.document_fact_span")
    fact_span.validate_container(document_text)
    if fact_span.quote(document_text) != fact_quote:
        raise ContractValidationError("canonical fact quote does not replay from document")
    source_hashes = [
        _hex_string(item, f"{label}.source_fact_hashes")
        for item in _sequence(fact.get("source_fact_hashes"), f"{label}.source_fact_hashes")
    ]
    if not source_hashes or len(source_hashes) != len(set(source_hashes)):
        raise ContractValidationError("canonical fact source hashes must be non-empty and unique")
    occurrences: list[dict[str, object]] = []
    occurrence_keys: set[tuple[str, int]] = set()
    referenced_hashes: set[str] = set()
    for occurrence_index, raw_binding in enumerate(
        _sequence(fact.get("source_occurrences"), f"{label}.source_occurrences")
    ):
        binding_label = f"{label}.source_occurrences[{occurrence_index}]"
        binding = _mapping(raw_binding, binding_label)
        if set(binding) != {
            "source_fact_hash",
            "source_occurrence_index",
            "source_occurrence",
        }:
            raise ContractValidationError(f"{binding_label} fields are invalid")
        source_fact_hash = _hex_string(
            binding.get("source_fact_hash"), f"{binding_label}.source_fact_hash"
        )
        source_index = _integer(
            binding.get("source_occurrence_index"),
            f"{binding_label}.source_occurrence_index",
        )
        if source_index < 0 or (source_fact_hash, source_index) in occurrence_keys:
            raise ContractValidationError("canonical fact source occurrence binding is invalid")
        if source_fact_hash not in source_hashes:
            raise ContractValidationError("source occurrence refers to an unlisted fact hash")
        occurrence_keys.add((source_fact_hash, source_index))
        referenced_hashes.add(source_fact_hash)
        occurrence = _mapping(binding.get("source_occurrence"), f"{binding_label}.source_occurrence")
        chunk_span = _span(
            occurrence.get("chunk_source_span"),
            f"{binding_label}.source_occurrence.chunk_source_span",
        )
        chunk_span.validate_container(document_text)
        chunk_hash = _hex_string(
            occurrence.get("chunk_hash"),
            f"{binding_label}.source_occurrence.chunk_hash",
        )
        if sha256_text(chunk_span.quote(document_text)) != chunk_hash:
            raise ContractValidationError("source occurrence chunk hash does not match document")
        evidence_quote = _string(
            occurrence.get("source_evidence_quote"),
            f"{binding_label}.source_occurrence.source_evidence_quote",
        )
        document_evidence_span = _span(
            occurrence.get("document_evidence_span"),
            f"{binding_label}.source_occurrence.document_evidence_span",
        )
        if document_evidence_span.quote(document_text) != evidence_quote:
            raise ContractValidationError("source evidence does not replay from document")
        chunk_evidence_span = _span(
            occurrence.get("chunk_evidence_span"),
            f"{binding_label}.source_occurrence.chunk_evidence_span",
        )
        if (
            chunk_span.start + chunk_evidence_span.start != document_evidence_span.start
            or chunk_span.start + chunk_evidence_span.end != document_evidence_span.end
        ):
            raise ContractValidationError("chunk and document evidence spans disagree")
        chunk_fact_span = _span(
            occurrence.get("chunk_fact_span"),
            f"{binding_label}.source_occurrence.chunk_fact_span",
        )
        if (
            chunk_span.start + chunk_fact_span.start != fact_span.start
            or chunk_span.start + chunk_fact_span.end != fact_span.end
        ):
            raise ContractValidationError("chunk and document fact spans disagree")
        occurrences.append(copy.deepcopy(dict(binding)))
    if not occurrences or referenced_hashes != set(source_hashes):
        raise ContractValidationError("every source fact hash must have an occurrence")
    occurrences.sort(key=_canonical_json)
    return {
        "canonical_fact_id": fact_id,
        "character_id": character_id,
        "fact_quote": fact_quote,
        "category": category,
        "attribute": attribute,
        "value": value,
        "document_fact_span": fact_span.to_dict(),
        "source_fact_hashes": sorted(source_hashes),
        "source_occurrences": occurrences,
    }


def _validate_labels(
    label_projection: Mapping[str, object],
    character_ids: set[str],
) -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, object]]]]:
    label_characters: dict[str, dict[str, object]] = {}
    seen_label_ids: set[str] = set()
    for index, raw_character in enumerate(
        _sequence(label_projection.get("characters"), "label_projection.characters")
    ):
        label = f"label_projection.characters[{index}]"
        character = _mapping(raw_character, label)
        if set(character) != {
            "character_id",
            "source_canonical_label",
            "source_canonical_label_status",
            "preferred_label_id",
            "labels",
        }:
            raise ContractValidationError(f"{label} fields are invalid")
        character_id = _string(character.get("character_id"), f"{label}.character_id")
        if character_id not in character_ids or character_id in label_characters:
            raise ContractValidationError("label projection character roster is invalid")
        _string(character.get("source_canonical_label"), f"{label}.source_canonical_label")
        if character.get("source_canonical_label_status") not in {
            "confirmed_name_like",
            "provisional_description",
        }:
            raise ContractValidationError("source canonical label status is unsupported")
        preferred_label_id = _string(
            character.get("preferred_label_id"), f"{label}.preferred_label_id"
        )
        labels: list[dict[str, object]] = []
        preferred_count = 0
        for label_index, raw_projected_label in enumerate(
            _sequence(character.get("labels"), f"{label}.labels")
        ):
            item_label = f"{label}.labels[{label_index}]"
            item = _mapping(raw_projected_label, item_label)
            if set(item) != {
                "label_id",
                "label_quote",
                "source_label_role",
                "label_kind",
                "label_stability",
                "source_globally_unique",
                "selection_status",
            }:
                raise ContractValidationError(f"{item_label} fields are invalid")
            label_id = _string(item.get("label_id"), f"{item_label}.label_id")
            if label_id in seen_label_ids:
                raise ContractValidationError("duplicate projected label id")
            seen_label_ids.add(label_id)
            _string(item.get("label_quote"), f"{item_label}.label_quote")
            if item.get("source_label_role") not in SOURCE_LABEL_ROLES:
                raise ContractValidationError("projected label source role is unsupported")
            if item.get("label_kind") not in LABEL_KINDS:
                raise ContractValidationError("projected label kind is unsupported")
            if item.get("label_stability") not in LABEL_STABILITIES:
                raise ContractValidationError("projected label stability is unsupported")
            if not isinstance(item.get("source_globally_unique"), bool):
                raise ContractValidationError("projected label source uniqueness must be boolean")
            if item.get("selection_status") not in {"preferred", "alternate"}:
                raise ContractValidationError("projected label selection status is unsupported")
            if item.get("selection_status") == "preferred":
                preferred_count += 1
                if label_id != preferred_label_id:
                    raise ContractValidationError("preferred projected label id is inconsistent")
            labels.append(copy.deepcopy(dict(item)))
        if preferred_count != 1:
            raise ContractValidationError("each character must have one preferred label")
        labels.sort(key=lambda item: (item["selection_status"] != "preferred", str(item["label_id"])))
        label_characters[character_id] = {
            "character_id": character_id,
            "preferred_label_id": preferred_label_id,
            "source_canonical_label": character["source_canonical_label"],
            "source_canonical_label_status": character["source_canonical_label_status"],
            "labels": labels,
        }
    if set(label_characters) != character_ids:
        raise ContractValidationError("label projection and fact group character rosters differ")

    actionable_by_character: dict[str, list[dict[str, object]]] = {
        character_id: [] for character_id in character_ids
    }
    seen_review_ids: set[str] = set()
    for index, raw_review in enumerate(
        _sequence(
            label_projection.get("actionable_review_items"),
            "label_projection.actionable_review_items",
        )
    ):
        review = _mapping(raw_review, f"actionable_review_items[{index}]")
        review_id = _string(review.get("review_item_id"), "actionable review id")
        character_id = _string(review.get("subject_character_id"), "actionable subject")
        if review_id in seen_review_ids or character_id not in character_ids:
            raise ContractValidationError("actionable review item is duplicate or has unknown subject")
        seen_review_ids.add(review_id)
        actionable_by_character[character_id].append(copy.deepcopy(dict(review)))
    for reviews in actionable_by_character.values():
        reviews.sort(key=lambda item: str(item["review_item_id"]))
    return label_characters, actionable_by_character


def _validate_sources(
    *,
    document_text: str,
    fact_groups: Mapping[str, object],
    appearance_states: Mapping[str, object],
    label_projection: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(document_text, str) or not document_text:
        raise ContractValidationError("document_text must be a non-empty string")
    if fact_groups.get("schema_version") != DOCUMENT_CHARACTER_FACT_GROUPS_VERSION:
        raise ContractValidationError("fact_groups schema_version is unsupported")
    if fact_groups.get("grouping_policy_version") != POST_LINK_FACT_GROUPING_POLICY_VERSION:
        raise ContractValidationError("fact_groups grouping policy is unsupported")
    if appearance_states.get("schema_version") != DOCUMENT_APPEARANCE_STATES_VERSION:
        raise ContractValidationError("appearance_states schema_version is unsupported")
    if appearance_states.get("transition_policy_version") != APPEARANCE_TRANSITION_POLICY_VERSION:
        raise ContractValidationError("appearance transition policy is unsupported")
    if appearance_states.get("state_segment_policy_version") != STATE_SEGMENT_POLICY_VERSION:
        raise ContractValidationError("state segment policy is unsupported")
    if appearance_states.get("relation_policy_version") != APPEARANCE_RELATION_POLICY_VERSION:
        raise ContractValidationError("appearance relation policy is unsupported")
    if appearance_states.get("normalization_policy_version") != APPEARANCE_PROPOSITION_POLICY_VERSION:
        raise ContractValidationError("appearance proposition policy is unsupported")
    if label_projection.get("schema_version") != DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION:
        raise ContractValidationError("label projection schema_version is unsupported")
    if label_projection.get("label_projection_policy_version") != LABEL_PROJECTION_POLICY_VERSION:
        raise ContractValidationError("label projection policy is unsupported")
    if label_projection.get("review_projection_policy_version") != REVIEW_PROJECTION_POLICY_VERSION:
        raise ContractValidationError("review projection policy is unsupported")

    source_document_version_id = _string(
        fact_groups.get("source_document_version_id"),
        "fact_groups.source_document_version_id",
    )
    if any(
        source.get("source_document_version_id") != source_document_version_id
        for source in (appearance_states, label_projection)
    ):
        raise ContractValidationError("render compiler sources refer to different documents")
    document_hash = _hex_string(fact_groups.get("document_hash"), "fact_groups.document_hash")
    if document_hash != sha256_text(document_text):
        raise ContractValidationError("fact_groups document hash does not match source text")
    if label_projection.get("document_hash") != document_hash:
        raise ContractValidationError("label projection document hash is inconsistent")
    if fact_groups.get("coverage_status") != "complete" or appearance_states.get("coverage_status") != "complete":
        raise ContractValidationError("render compiler requires complete source coverage")
    processed_source_end = _integer(
        appearance_states.get("processed_source_end"),
        "appearance_states.processed_source_end",
    )
    if (
        processed_source_end != len(document_text)
        or fact_groups.get("processed_source_end") != processed_source_end
    ):
        raise ContractValidationError("render compiler sources do not cover the full document")

    character_fact_ids: dict[str, set[str]] = {}
    for index, raw_character in enumerate(
        _sequence(fact_groups.get("characters"), "fact_groups.characters")
    ):
        character = _mapping(raw_character, f"fact_groups.characters[{index}]")
        character_id = _string(character.get("character_id"), "fact group character_id")
        if character_id in character_fact_ids:
            raise ContractValidationError("duplicate fact group character")
        raw_ids = _sequence(character.get("canonical_fact_ids"), "canonical_fact_ids")
        ids = {_string(item, "canonical_fact_ids[]") for item in raw_ids}
        if len(ids) != len(raw_ids):
            raise ContractValidationError("duplicate fact id in character roster")
        character_fact_ids[character_id] = ids
    if not character_fact_ids:
        raise ContractValidationError("render compiler requires at least one character")

    facts: dict[str, dict[str, object]] = {}
    actual_fact_ids: dict[str, set[str]] = {
        character_id: set() for character_id in character_fact_ids
    }
    for index, raw_fact in enumerate(
        _sequence(fact_groups.get("fact_groups"), "fact_groups.fact_groups")
    ):
        fact = _validate_fact_provenance(
            document_text=document_text,
            fact=_mapping(raw_fact, f"fact_groups.fact_groups[{index}]"),
            label=f"fact_groups.fact_groups[{index}]",
        )
        fact_id = str(fact["canonical_fact_id"])
        character_id = str(fact["character_id"])
        if fact_id in facts or character_id not in character_fact_ids:
            raise ContractValidationError("canonical fact is duplicate or has unknown character")
        facts[fact_id] = fact
        actual_fact_ids[character_id].add(fact_id)
    if actual_fact_ids != character_fact_ids:
        raise ContractValidationError("fact group roster and facts differ")

    transitions = [
        _mapping(item, f"appearance_states.transitions[{index}]")
        for index, item in enumerate(
            _sequence(appearance_states.get("transitions"), "appearance_states.transitions")
        )
    ]
    rebuilt_transitions = attach_transition_ids(
        document_text=document_text,
        source_document_version_id=source_document_version_id,
        transition_policy_version=APPEARANCE_TRANSITION_POLICY_VERSION,
        transitions=transitions,
    )
    if _normalize_unordered(transitions) != _normalize_unordered(list(rebuilt_transitions)):
        raise ContractValidationError("appearance transitions are not reproducible")

    assignments = [
        _mapping(item, f"appearance_states.fact_assignments[{index}]")
        for index, item in enumerate(
            _sequence(
                appearance_states.get("fact_assignments"),
                "appearance_states.fact_assignments",
            )
        )
    ]
    state_segments = [
        _mapping(item, f"appearance_states.state_segments[{index}]")
        for index, item in enumerate(
            _sequence(
                appearance_states.get("state_segments"),
                "appearance_states.state_segments",
            )
        )
    ]
    rebuilt_segments = build_character_state_segments(
        document_text=document_text,
        source_document_version_id=source_document_version_id,
        chapters=parse_document_chapters(document_text),
        fact_groups=fact_groups,
        fact_assignments=assignments,
        transitions=rebuilt_transitions,
    )
    if _normalize_unordered(state_segments) != _normalize_unordered(list(rebuilt_segments)):
        raise ContractValidationError("state segments are not reproducible")

    semantic = build_appearance_semantic_projection(
        source_document_version_id=source_document_version_id,
        document_length=len(document_text),
        fact_groups=fact_groups,
        fact_assignments=assignments,
        state_segments=state_segments,
    )
    source_relations = list(
        _sequence(appearance_states.get("relations"), "appearance_states.relations")
    )
    source_propositions = list(
        _sequence(
            appearance_states.get("normalized_propositions"),
            "appearance_states.normalized_propositions",
        )
    )
    if _normalize_unordered(source_relations) != _normalize_unordered(semantic["relations"]):
        raise ContractValidationError("appearance relations are not reproducible")
    if _normalize_unordered(source_propositions) != _normalize_unordered(
        semantic["normalized_propositions"]
    ):
        raise ContractValidationError("appearance propositions are not reproducible")

    label_characters, actionable_by_character = _validate_labels(
        label_projection, set(character_fact_ids)
    )
    assignments_by_id = {
        str(assignment["canonical_fact_id"]): assignment for assignment in assignments
    }
    if set(assignments_by_id) != set(facts):
        raise ContractValidationError("fact assignments and facts differ")
    segments_by_character: dict[str, list[Mapping[str, object]]] = {
        character_id: [] for character_id in character_fact_ids
    }
    fact_to_segment: dict[str, Mapping[str, object]] = {}
    for segment in state_segments:
        character_id = str(segment["character_id"])
        segments_by_character[character_id].append(segment)
        for fact_id in segment["observed_fact_ids"]:
            fact_to_segment[str(fact_id)] = segment
    for segments in segments_by_character.values():
        segments.sort(key=lambda item: int(item["sequence_index"]))
    propositions_by_character: dict[str, list[Mapping[str, object]]] = {
        character_id: [] for character_id in character_fact_ids
    }
    for proposition in semantic["normalized_propositions"]:
        propositions_by_character[str(proposition["character_id"])].append(proposition)
    relations_by_character: dict[str, list[Mapping[str, object]]] = {
        character_id: [] for character_id in character_fact_ids
    }
    for relation in semantic["relations"]:
        relations_by_character[str(relation["character_id"])].append(relation)
    transitions_by_character: dict[str, list[Mapping[str, object]]] = {
        character_id: [] for character_id in character_fact_ids
    }
    for transition in rebuilt_transitions:
        character_id = str(transition["character_id"])
        if character_id not in transitions_by_character:
            raise ContractValidationError("transition references unknown character")
        transitions_by_character[character_id].append(transition)
    return {
        "source_document_version_id": source_document_version_id,
        "document_hash": document_hash,
        "processed_source_end": processed_source_end,
        "chapters": parse_document_chapters(document_text),
        "identity_status_by_character": {str(c["character_id"]): c.get("identity_status", "unknown") for c in fact_groups["characters"]},
        "facts": facts,
        "assignments": assignments_by_id,
        "fact_to_segment": fact_to_segment,
        "segments_by_character": segments_by_character,
        "propositions_by_character": propositions_by_character,
        "relations_by_character": relations_by_character,
        "transitions_by_character": transitions_by_character,
        "label_characters": label_characters,
        "actionable_by_character": actionable_by_character,
    }


def _validate_request(
    value: object,
    index: int,
    *,
    character_ids: set[str],
    document_length: int,
) -> dict[str, object]:
    request = _mapping(value, f"requests[{index}]")
    if set(request) != {"character_id", "selector"}:
        raise ContractValidationError("render request must contain only character_id/selector")
    character_id = _string(request.get("character_id"), f"requests[{index}].character_id")
    if character_id not in character_ids:
        raise ContractValidationError("render request references unknown character")
    selector = _mapping(request.get("selector"), f"requests[{index}].selector")
    if set(selector) != {*_SELECTOR_FIELDS, "document_position"}:
        raise ContractValidationError("render selector fields are invalid")
    normalized_selector: dict[str, object] = {}
    for field in _SELECTOR_FIELDS:
        raw = selector.get(field)
        normalized_selector[field] = None if raw is None else _string(raw, field)
    position = selector.get("document_position")
    if position is not None:
        position = _integer(position, "selector.document_position")
        if not 0 <= position < document_length:
            raise ContractValidationError("selector document_position is outside coverage")
    normalized_selector["document_position"] = position
    return {"character_id": character_id, "selector": normalized_selector}


def _chapter_for_position(chapters: Sequence[Mapping[str, object]], position: int) -> int:
    for chapter in chapters:
        span = _span(chapter.get("document_span"), "chapter.document_span")
        if span.start <= position < span.end:
            return _integer(chapter.get("chapter_number"), "chapter.chapter_number")
    raise ContractValidationError("selector position does not belong to a chapter")


def _relevant_transitions(
    transitions: Sequence[Mapping[str, object]],
    document_position: int,
) -> list[dict[str, object]]:
    eligible = [
        transition
        for transition in transitions
        if transition_effective_position(transition) <= document_position
    ]
    life = [item for item in eligible if item["dimension"] == "life"]
    latest_life = max(life, key=transition_effective_position) if life else None
    life_cutoff = transition_effective_position(latest_life) if latest_life else 0
    form = [
        item
        for item in eligible
        if item["dimension"] == "form"
        and transition_effective_position(item) >= life_cutoff
    ]
    latest_form = max(form, key=transition_effective_position) if form else None
    state_cutoff = max(
        life_cutoff,
        transition_effective_position(latest_form) if latest_form else 0,
    )
    related: dict[str, Mapping[str, object]] = {}
    for transition in (latest_life, latest_form):
        if transition is not None:
            related[str(transition["transition_id"])] = transition
    for transition in eligible:
        if (
            transition["dimension"] == "appearance"
            and transition_effective_position(transition) >= state_cutoff
        ):
            related[str(transition["transition_id"])] = transition
    return [
        copy.deepcopy(dict(item))
        for item in sorted(
            related.values(),
            key=lambda item: (transition_effective_position(item), str(item["transition_id"])),
        )
    ]


def _project_relation_outcomes(
    *,
    relations: Sequence[Mapping[str, object]],
    included_fact_ids: set[str],
    applicability: Mapping[str, tuple[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    unresolved_conflicts: list[dict[str, object]] = []
    relation_warning_ids: dict[str, list[str]] = {}
    for relation in relations:
        left_id = str(relation["left_fact_id"])
        right_id = str(relation["right_fact_id"])
        if left_id not in included_fact_ids or right_id not in included_fact_ids:
            continue
        related_ids = [str(relation["relation_id"]), left_id, right_id]
        both_active = applicability[left_id][0] == applicability[right_id][0] == "active"
        if relation["relation"] in {"true_conflict", "incompatible"}:
            if both_active:
                unresolved_conflicts.append(
                    {**copy.deepcopy(dict(relation)), "relation": "true_conflict", "applicability_status": "active_overlap"}
                )
            else:
                relation_warning_ids.setdefault(
                    "provisional_incompatible_relation" if relation["relation"] == "incompatible" else "provisional_true_conflict_overlap", []
                ).extend(related_ids)
        elif relation["relation"] == "unclassified":
            relation_warning_ids.setdefault(
                "active_unclassified_relation"
                if both_active
                else "provisional_unclassified_relation",
                [],
            ).extend(related_ids)

    relation_warning_messages = {
        "provisional_incompatible_relation": "Semantic incompatibility has uncertain temporal overlap; review required.",
        "active_unclassified_relation": (
            "One or more active in-scope relations remain unclassified and were not forced into a conflict class."
        ),
        "provisional_unclassified_relation": (
            "One or more in-scope relations have provisional applicability and remain unclassified."
        ),
        "provisional_true_conflict_overlap": (
            "One or more true-conflict relations include provisional applicability and were not promoted to unresolved_conflicts."
        ),
    }
    warnings = [
        _warning(code, relation_warning_messages[code], related_ids)
        for code, related_ids in relation_warning_ids.items()
    ]
    unresolved_conflicts.sort(key=lambda item: str(item["relation_id"]))
    warnings.sort(key=lambda item: str(item["code"]))
    return unresolved_conflicts, warnings


def _empty_profile(
    *,
    profile_id: str,
    request: Mapping[str, object],
    identity_labels: Mapping[str, object],
    status: str,
    candidate_segment_ids: Sequence[str],
    warnings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "profile_id": profile_id,
        "character_id": request["character_id"],
        "selector": copy.deepcopy(dict(_mapping(request["selector"], "selector"))),
        "compile_status": status,
        "candidate_state_segment_ids": sorted(candidate_segment_ids),
        "selected_state_segment_id": None,
        "selected_state": None,
        "identity_labels": copy.deepcopy(dict(identity_labels)),
        "active_fact_ids": [],
        "provisional_fact_ids": [],
        "stable_traits": [],
        "variant_traits": [],
        "scene_overrides": [],
        "transitions": [],
        "unresolved_conflicts": [],
        "provenance": [],
        "compile_warnings": [copy.deepcopy(dict(item)) for item in warnings],
    }


def _compile_state_projection(
    *,
    source_document_version_id: str,
    request: Mapping[str, object],
    context: Mapping[str, object],
) -> dict[str, object]:
    character_id = str(request["character_id"])
    selector = _mapping(request["selector"], "request.selector")
    profile_id = _stable_id(
        "render-profile",
        {
            "source_document_version_id": source_document_version_id,
            "artifact_set_id": context["artifact_set_id"],
            "compiler_policy_version": RENDER_PROFILE_COMPILER_POLICY_VERSION,
            "applicability_policy_version": FACT_APPLICABILITY_POLICY_VERSION,
            "character_id": character_id,
            "selector": selector,
        },
    )
    segments = list(context["segments_by_character"][character_id])
    candidates = select_state_segments(segments, selector)
    document_position = selector["document_position"]
    identity_labels = context["label_characters"][character_id]
    if not candidates:
        return _empty_profile(
            profile_id=profile_id,
            request=request,
            identity_labels=identity_labels,
            status="no_matching_state",
            candidate_segment_ids=(),
            warnings=(
                _warning(
                    "selector_no_match",
                    "The selector does not match any state segment for this character.",
                ),
            ),
        )
    if document_position is None or len(candidates) != 1:
        warnings = [
            _warning(
                "selector_missing_document_position",
                "document_position is required before traits can be compiled without future observations.",
            )
        ]
        if len(candidates) != 1:
            warnings.append(
                _warning(
                    "selector_ambiguous",
                    "The selector matches multiple state segments; no traits were mixed.",
                    [str(item["state_segment_id"]) for item in candidates],
                )
            )
        return _empty_profile(
            profile_id=profile_id,
            request=request,
            identity_labels=identity_labels,
            status="selector_required",
            candidate_segment_ids=[str(item["state_segment_id"]) for item in candidates],
            warnings=warnings,
        )

    selected = candidates[0]
    selected_chapter = _chapter_for_position(context["chapters"], int(document_position))
    facts = context["facts"]
    assignments = context["assignments"]
    fact_to_segment = context["fact_to_segment"]
    transitions = context["transitions_by_character"][character_id]
    applicability: dict[str, tuple[str, str]] = {}
    details = []
    for fact_id in sorted(context["character_fact_ids"][character_id]):
        result = evaluate_fact_applicability(
            fact=facts[fact_id],
            assignment=assignments[fact_id],
            observed_segment=fact_to_segment[fact_id],
            target_segment=selected,
            segments=segments,
            transitions=transitions,
            document_position=int(document_position),
            selected_chapter=selected_chapter,
            events=context.get("applicability_events", ()),
            candidate_facts=list(facts.values()),
            scene_events=context.get("scene_events", ()),
        )
        details.append(result)
        if result["status"] != "excluded":
            applicability[fact_id] = (result["status"], result["reason"])
    active_fact_ids = sorted(
        (fact_id for fact_id, value in applicability.items() if value[0] == "active"),
        key=lambda fact_id: (
            _span(facts[fact_id]["document_fact_span"], "fact span").start,
            fact_id,
        ),
    )
    provisional_fact_ids = sorted(
        (fact_id for fact_id, value in applicability.items() if value[0] == "provisional"),
        key=lambda fact_id: (
            _span(facts[fact_id]["document_fact_span"], "fact span").start,
            fact_id,
        ),
    )
    included_fact_ids = set(active_fact_ids) | set(provisional_fact_ids)

    stable_traits: list[dict[str, object]] = []
    variant_traits: list[dict[str, object]] = []
    scene_overrides: list[dict[str, object]] = []
    for proposition in context["propositions_by_character"][character_id]:
        member_ids = [
            str(fact_id)
            for fact_id in proposition["member_fact_ids"]
            if str(fact_id) in included_fact_ids
        ]
        if not member_ids:
            continue
        member_ids.sort(
            key=lambda fact_id: (
                _span(facts[fact_id]["document_fact_span"], "fact span").start,
                fact_id,
            )
        )
        statuses = {applicability[fact_id][0] for fact_id in member_ids}
        trait_status = "active" if statuses == {"active"} else "provisional"
        persistence_values = sorted(
            {str(assignments[fact_id]["persistence"]) for fact_id in member_ids},
            key=_PERSISTENCE_ORDER.__getitem__,
        )
        trait = {
            "trait_id": _stable_id(
                "render-trait",
                {
                    "profile_id": profile_id,
                    "source_proposition_id": proposition["proposition_id"],
                    "canonical_fact_ids": member_ids,
                    "applicability_status": trait_status,
                },
            ),
            "attribute": proposition["attribute"],
            "value": proposition["normalized_value"],
            "categories": sorted(str(item) for item in proposition["categories"]),
            "source_proposition_id": proposition["proposition_id"],
            "canonical_fact_ids": member_ids,
            "persistence": persistence_values,
            "applicability_status": trait_status,
        }
        if any(value in {"scene", "momentary"} for value in persistence_values):
            scene_overrides.append(trait)
        elif persistence_values == ["stable"]:
            stable_traits.append(trait)
        else:
            variant_traits.append(trait)

    trait_sort_key = lambda item: (
        min(
            _span(facts[fact_id]["document_fact_span"], "fact span").start
            for fact_id in item["canonical_fact_ids"]
        ),
        str(item["trait_id"]),
    )
    stable_traits.sort(key=trait_sort_key)
    variant_traits.sort(key=trait_sort_key)
    scene_overrides.sort(key=trait_sort_key)

    warnings: list[dict[str, object]] = []
    for output_field, segment_field in _SELECTOR_FIELDS.items():
        if selected[segment_field] == "unknown":
            warnings.append(
                _warning(
                    f"unknown_{segment_field}_state",
                    f"The selected segment has unknown {output_field}; no value was inferred.",
                    [str(selected["state_segment_id"])],
                )
            )
    if provisional_fact_ids:
        warnings.append(
            _warning(
                "provisional_fact_applicability",
                "Some traits have unknown or scene-bounded persistence and remain provisional.",
                provisional_fact_ids,
            )
        )

    adjudicated_pairs = {frozenset(r["fact_ids"]) for r in context.get("semantic_evidence", ())
                        if r["character_id"] == character_id and r["relation"] != "uncertain"}
    unresolved_conflicts, relation_warnings = _project_relation_outcomes(
        relations=[r for r in context["relations_by_character"][character_id]
                   if r["relation"] != "unclassified"
                   or frozenset((r["left_fact_id"], r["right_fact_id"])) not in adjudicated_pairs] + [
            {**r, "state_segment_id": selected["state_segment_id"]} for r in context.get("incompatibilities", ())
            if r["character_id"] == character_id],
        included_fact_ids=included_fact_ids,
        applicability=applicability,
    )
    warnings.extend(relation_warnings)
    if context.get("semantic_reviews"):
        warnings.append(_warning("automatic_semantic_review", "Automatic semantic outputs contain rejected items requiring review."))

    actionable_reviews = context["actionable_by_character"][character_id]
    if actionable_reviews:
        warnings.append(
            _warning(
                "actionable_identity_review",
                "The character still has an actionable identity review in the final projection.",
                [str(item["review_item_id"]) for item in actionable_reviews],
            )
        )
    warnings.sort(key=lambda item: (str(item["code"]), _canonical_json(item["related_ids"])))
    unresolved_conflicts.sort(key=lambda item: str(item["relation_id"]))

    provenance = [
        {
            "canonical_fact_id": fact_id,
            "fact_quote": facts[fact_id]["fact_quote"],
            "category": facts[fact_id]["category"],
            "attribute": facts[fact_id]["attribute"],
            "value": facts[fact_id]["value"],
            "document_fact_span": copy.deepcopy(facts[fact_id]["document_fact_span"]),
            "source_fact_hashes": copy.deepcopy(facts[fact_id]["source_fact_hashes"]),
            "source_occurrences": copy.deepcopy(facts[fact_id]["source_occurrences"]),
            "applicability_status": applicability[fact_id][0],
            "applicability_reason": applicability[fact_id][1],
        }
        for fact_id in active_fact_ids + provisional_fact_ids
    ]
    provenance.sort(
        key=lambda item: (
            int(_mapping(item["document_fact_span"], "provenance span")["start"]),
            str(item["canonical_fact_id"]),
        )
    )
    selected_span = _span(selected["document_span"], "selected state span")
    return {
        "profile_id": profile_id,
        "character_id": character_id,
        "selector": copy.deepcopy(dict(selector)),
        "compile_status": "compiled_with_warnings" if warnings else "compiled",
        "candidate_state_segment_ids": [str(selected["state_segment_id"])],
        "selected_state_segment_id": selected["state_segment_id"],
        "selected_state": {
            "life_stage": selected["life"],
            "form_state": selected["form"],
            "scene_state": selected["scene"],
            "chapter_number": selected_chapter,
            "document_span": selected_span.to_dict(),
        },
        "identity_labels": copy.deepcopy(dict(identity_labels)),
        "active_fact_ids": active_fact_ids,
        "provisional_fact_ids": provisional_fact_ids,
        "stable_traits": stable_traits,
        "variant_traits": variant_traits,
        "scene_overrides": scene_overrides,
        "transitions": _relevant_transitions(transitions, int(document_position)),
        "unresolved_conflicts": unresolved_conflicts,
        "provenance": provenance,
        "compile_warnings": warnings,
        "applicability": details,
    }


def build_render_ready_character_profiles(
    *,
    document_text: str,
    fact_groups: Mapping[str, object],
    appearance_states: Mapping[str, object],
    label_projection: Mapping[str, object],
    requests: Sequence[Mapping[str, object]],
    applicability_events: Mapping[str, object] | None = None,
    automatic_semantics: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Compile deterministic, state-selected character cards from immutable sources."""
    context = _validate_sources(
        document_text=document_text,
        fact_groups=_mapping(fact_groups, "fact_groups"),
        appearance_states=_mapping(appearance_states, "appearance_states"),
        label_projection=_mapping(label_projection, "label_projection"),
    )
    context["applicability_events"] = validate_applicability_events(
        applicability_events, document_text=document_text,
        source_document_version_id=str(context["source_document_version_id"]), facts=context["facts"],
    )
    _attach_automatic_semantics(context, automatic_semantics, document_text, fact_groups)
    context["artifact_set_id"] = _artifact_set_id(fact_groups, appearance_states, label_projection,
                                               context["applicability_events"])
    if automatic_semantics is not None:
        context["artifact_set_id"] = _stable_id("artifact-set", {"base": context["artifact_set_id"], "semantics": automatic_semantics})
    normalized_requests = [
        _validate_request(
            request,
            index,
            character_ids=set(context["segments_by_character"]),
            document_length=int(context["processed_source_end"]),
        )
        for index, request in enumerate(requests)
    ]
    if not normalized_requests:
        raise ContractValidationError("render compiler requires at least one request")
    request_keys = [_canonical_json(request) for request in normalized_requests]
    if len(request_keys) != len(set(request_keys)):
        raise ContractValidationError("render compiler contains duplicate requests")
    context["character_fact_ids"] = {
        character_id: {
            fact_id
            for fact_id, fact in context["facts"].items()
            if fact["character_id"] == character_id
        }
        for character_id in context["segments_by_character"]
    }
    profiles = [
        snapshot_to_render_profile(_compile_snapshot(
            request=request, context=context, run_id="legacy-render",
        ))
        for request in normalized_requests
    ]
    profiles.sort(key=lambda item: str(item["profile_id"]))
    statuses = {
        status: sum(profile["compile_status"] == status for profile in profiles)
        for status in PROFILE_STATUSES
    }
    result = {
        "schema_version": RENDER_READY_CHARACTER_PROFILES_VERSION,
        "compiler_policy_version": RENDER_PROFILE_COMPILER_POLICY_VERSION,
        "applicability_policy_version": FACT_APPLICABILITY_POLICY_VERSION,
        "source_document_version_id": context["source_document_version_id"],
        "document_hash": context["document_hash"],
        "source_fact_groups_version": DOCUMENT_CHARACTER_FACT_GROUPS_VERSION,
        "source_fact_groups_hash": _order_independent_hash(fact_groups),
        "source_appearance_states_version": DOCUMENT_APPEARANCE_STATES_VERSION,
        "source_appearance_states_hash": _order_independent_hash(appearance_states),
        "source_label_projection_version": DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION,
        "source_label_projection_hash": _order_independent_hash(label_projection),
        "source_requests_hash": _order_independent_hash(
            {"schema_version": RENDER_PROFILE_REQUESTS_VERSION, "requests": normalized_requests}
        ),
        "profiles": profiles,
        "summary": {
            "requests": len(profiles),
            "compiled_profiles": statuses["compiled"] + statuses["compiled_with_warnings"],
            "compiled_with_warnings": statuses["compiled_with_warnings"],
            "selector_required_profiles": statuses["selector_required"],
            "no_matching_state_profiles": statuses["no_matching_state"],
            "active_fact_bindings": sum(len(item["active_fact_ids"]) for item in profiles),
            "provisional_fact_bindings": sum(
                len(item["provisional_fact_ids"]) for item in profiles
            ),
            "stable_traits": sum(len(item["stable_traits"]) for item in profiles),
            "variant_traits": sum(len(item["variant_traits"]) for item in profiles),
            "scene_overrides": sum(len(item["scene_overrides"]) for item in profiles),
            "transitions": sum(len(item["transitions"]) for item in profiles),
            "unresolved_conflicts": sum(
                len(item["unresolved_conflicts"]) for item in profiles
            ),
            "compile_warnings": sum(len(item["compile_warnings"]) for item in profiles),
            "model_calls": 0,
            "all_requests_compiled": all(
                item["compile_status"] in {"compiled", "compiled_with_warnings"}
                for item in profiles
            ),
            "complete": True,
        },
    }
    return result


def run_render_ready_character_profiles(
    *,
    document_text: str,
    fact_groups_file: Path,
    appearance_states_file: Path,
    label_projection_file: Path,
    requests_file: Path,
    output_file: Path,
    applicability_events_file: Path | None = None,
    automatic_semantics_file: Path | None = None,
) -> dict[str, object]:
    requests_payload = _read_json(requests_file)
    if set(requests_payload) != {"schema_version", "requests"}:
        raise ContractValidationError("render requests artifact fields are invalid")
    if requests_payload.get("schema_version") != RENDER_PROFILE_REQUESTS_VERSION:
        raise ContractValidationError("render requests schema_version is unsupported")
    requests = [
        _mapping(item, f"requests[{index}]")
        for index, item in enumerate(
            _sequence(requests_payload.get("requests"), "requests")
        )
    ]
    result = build_render_ready_character_profiles(
        document_text=document_text,
        fact_groups=_read_json(fact_groups_file),
        appearance_states=_read_json(appearance_states_file),
        label_projection=_read_json(label_projection_file),
        requests=requests,
        applicability_events=_read_json(applicability_events_file) if applicability_events_file else None,
        automatic_semantics=_read_json(automatic_semantics_file) if automatic_semantics_file else None,
    )
    _write_json(output_file, result)
    return copy.deepcopy(dict(_mapping(result["summary"], "summary")))


def _artifact_set_id(fact_groups, appearance_states, label_projection, events) -> str:
    return _stable_id("artifact-set", {
        "facts": _order_independent_hash(fact_groups),
        "states": _order_independent_hash(appearance_states),
        "labels": _order_independent_hash(label_projection),
        "events": events,
        "applicability_policy": FACT_APPLICABILITY_POLICY_VERSION,
        "snapshot_policy": CHARACTER_SNAPSHOT_POLICY_VERSION,
    })


def _compile_snapshot(*, request, context, run_id) -> dict[str, object]:
    projection = _compile_state_projection(
        source_document_version_id=context["source_document_version_id"],
        request=request, context=context,
    )
    traits = []
    for kind in ("stable_traits", "variant_traits", "scene_overrides"):
        traits.extend({**trait, "kind": kind} for trait in projection.pop(kind))
    details = projection.pop("applicability", [])
    character_id = request["character_id"]
    if projection["selected_state_segment_id"] is None:
        details = [{"canonical_fact_id": fid, "status": "excluded",
                    "reason": projection["compile_status"],
                    "observation_span": dict(context["facts"][fid]["document_fact_span"]),
                    "valid_interval": {"start": context["facts"][fid]["document_fact_span"]["start"], "end": None},
                    "basis_event_ids": [], "persistence": context["assignments"][fid]["persistence"]}
                   for fid in sorted(context["character_fact_ids"][character_id])]
    excluded = [item for item in details if item["status"] == "excluded"]
    return {
        "schema_version": CHARACTER_SNAPSHOT_VERSION,
        "policy_version": CHARACTER_SNAPSHOT_POLICY_VERSION,
        "applicability_policy_version": FACT_APPLICABILITY_POLICY_VERSION,
        "snapshot_id": _stable_id("snapshot", {
            "artifact_set_id": context["artifact_set_id"], "run_id": run_id, "request": request,
        }),
        "artifact_set_id": context["artifact_set_id"],
        "run_id": run_id,
        "source_document_version_id": context["source_document_version_id"],
        "document_hash": context["document_hash"],
        "offset_unit": "unicode_codepoint",
        "identity_status": context["identity_status_by_character"][character_id],
        **projection,
        "active_traits": [t for t in traits if t["applicability_status"] == "active"],
        "provisional_traits": [t for t in traits if t["applicability_status"] == "provisional"],
        "applicability": [item for item in details if item["status"] != "excluded"],
        "excluded_facts": excluded,
        "semantic_evidence": [r for r in context.get("semantic_evidence", []) if r["character_id"] == character_id],
        "semantic_events": [e for e in context.get("semantic_events", []) if e["character_id"] == character_id],
        "semantic_reviews": context.get("semantic_reviews", []),
        "narrative_scene": _narrative_scene(context, character_id, request["selector"]["document_position"]),
        "review_refs": sorted(str(r["review_item_id"]) for r in context["actionable_by_character"][character_id]),
        "applicability_events": [copy.deepcopy(e) for e in context["applicability_events"]
                                 if e["character_id"] == character_id
                                 and request["selector"]["document_position"] is not None
                                 and (e["document_span"]["start"] if e["kind"] == "continuity"
                                      else e["document_span"]["end"]) <= request["selector"]["document_position"]],
    }


def snapshot_to_render_profile(snapshot: Mapping[str, object]) -> dict[str, object]:
    """Keep the existing card shape, without a second applicability calculation."""
    fields = (
        "profile_id", "character_id", "selector", "compile_status", "candidate_state_segment_ids",
        "selected_state_segment_id", "selected_state", "identity_labels", "active_fact_ids",
        "provisional_fact_ids", "transitions", "unresolved_conflicts", "provenance", "compile_warnings",
    )
    profile = {key: copy.deepcopy(snapshot[key]) for key in fields}
    starts = {p["canonical_fact_id"]: p["document_fact_span"]["start"] for p in snapshot["provenance"]}
    for kind in ("stable_traits", "variant_traits", "scene_overrides"):
        members = [t for t in snapshot["active_traits"] + snapshot["provisional_traits"] if t["kind"] == kind]
        members.sort(key=lambda t: (min(starts[i] for i in t["canonical_fact_ids"]), t["trait_id"]))
        profile[kind] = [{k: copy.deepcopy(v) for k, v in t.items() if k != "kind"} for t in members]
    return profile


def build_character_snapshot(
    *, document_text: str, fact_groups: Mapping[str, object],
    appearance_states: Mapping[str, object], label_projection: Mapping[str, object],
    run_id: str, character_id: str, document_position: int | None,
    life_stage: str | None = None, form_state: str | None = None, scene_state: str | None = None,
    applicability_events: Mapping[str, object] | None = None, explain: bool = False,
    automatic_semantics: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Read-only run-scoped snapshot. No provider, mutation or hidden model calls."""
    run_id = _string(run_id, "run_id")
    if not isinstance(explain, bool):
        raise ContractValidationError("explain must be boolean")
    context = _validate_sources(document_text=document_text, fact_groups=_mapping(fact_groups, "fact_groups"),
                                appearance_states=_mapping(appearance_states, "appearance_states"),
                                label_projection=_mapping(label_projection, "label_projection"))
    context["character_fact_ids"] = {
        cid: {fid for fid, f in context["facts"].items() if f["character_id"] == cid}
        for cid in context["segments_by_character"]
    }
    context["applicability_events"] = validate_applicability_events(
        applicability_events, document_text=document_text,
        source_document_version_id=context["source_document_version_id"], facts=context["facts"],
    )
    _attach_automatic_semantics(context, automatic_semantics, document_text, fact_groups)
    context["artifact_set_id"] = _artifact_set_id(fact_groups, appearance_states, label_projection,
                                               context["applicability_events"])
    if automatic_semantics is not None:
        context["artifact_set_id"] = _stable_id("artifact-set", {"base": context["artifact_set_id"], "semantics": automatic_semantics})
    request = _validate_request({"character_id": character_id, "selector": {
        "life_stage": life_stage, "form_state": form_state, "scene_state": scene_state,
        "document_position": document_position,
    }}, 0, character_ids=set(context["segments_by_character"]), document_length=len(document_text))
    snapshot = _compile_snapshot(request=request, context=context, run_id=run_id)
    if not explain:
        snapshot.pop("excluded_facts")
    else:
        for item in snapshot["excluded_facts"]:
            fact = context["facts"][item["canonical_fact_id"]]
            item["provenance"] = {k: copy.deepcopy(fact[k]) for k in (
                "fact_quote", "document_fact_span", "source_fact_hashes", "source_occurrences",
            )}
    return snapshot


def run_character_snapshot(
    *, document_text: str, fact_groups_file: Path, appearance_states_file: Path,
    label_projection_file: Path, output_file: Path, run_id: str, character_id: str,
    document_position: int | None, life_stage: str | None = None,
    form_state: str | None = None, scene_state: str | None = None,
    applicability_events_file: Path | None = None, explain: bool = False,
    automatic_semantics_file: Path | None = None,
) -> dict[str, object]:
    result = build_character_snapshot(
        document_text=document_text, fact_groups=_read_json(fact_groups_file),
        appearance_states=_read_json(appearance_states_file), label_projection=_read_json(label_projection_file),
        run_id=run_id, character_id=character_id, document_position=document_position,
        life_stage=life_stage, form_state=form_state, scene_state=scene_state,
        applicability_events=_read_json(applicability_events_file) if applicability_events_file else None,
        automatic_semantics=_read_json(automatic_semantics_file) if automatic_semantics_file else None,
        explain=explain,
    )
    # Explicit output cannot overwrite any immutable source input.
    if output_file.resolve() in {p.resolve() for p in (
        fact_groups_file, appearance_states_file, label_projection_file, applicability_events_file, automatic_semantics_file,
    ) if p is not None}:
        raise ContractValidationError("snapshot output must not overwrite a source artifact")
    _write_json(output_file, result)
    return {"snapshot_id": result["snapshot_id"], "compile_status": result["compile_status"],
            "active_traits": len(result["active_traits"]), "provisional_traits": len(result["provisional_traits"]),
            "model_calls": 0}


def _attach_automatic_semantics(context, artifact, text, groups):
    from .automatic_semantics import validate_automatic_semantics
    events, relations, scenes, wear = validate_automatic_semantics(
        artifact, document_text=text, fact_groups=groups, facts=context["facts"],
    )
    context["applicability_events"] = sorted(
        {e["event_id"]: e for e in context["applicability_events"] + events}.values(), key=lambda e: e["event_id"])
    context["incompatibilities"] = relations
    context["scene_events"] = scenes
    context["semantic_evidence"] = artifact["relations"] if artifact else []
    context["semantic_reviews"] = artifact["reviews"] if artifact else []
    context["semantic_events"] = artifact["events"] if artifact else []


def _narrative_scene(context, character_id, position):
    if position is None:
        return None
    life_positions = [transition_effective_position(t) for t in context["transitions_by_character"][character_id]
                      if t["dimension"] == "life" and transition_effective_position(t) <= position]
    cutoff = max(life_positions, default=0)
    scenes = [e for e in context.get("scene_events", ()) if e["character_id"] == character_id
              and e["document_span"]["end"] >= cutoff]
    prior = [e for e in scenes if e["document_span"]["end"] <= position]
    latest = max(prior, key=lambda e: (e["document_span"]["end"], e["event_id"])) if prior else None
    future = [e["document_span"]["end"] for e in scenes if e["document_span"]["end"] > position]
    return {"status": "grounded_boundary" if latest else "unknown", "boundary_event": latest,
            "document_span": {"start": latest["document_span"]["end"] if latest else cutoff,
                              "end": min(future) if future else None}}
