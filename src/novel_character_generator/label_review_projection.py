from __future__ import annotations

import copy
import json
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

from .errors import ContractValidationError
from .identity import (
    IDENTITY_COMPATIBLE_CANDIDATE_POLICY_VERSIONS,
    IDENTITY_CONFLICT_POLICY_VERSION,
    IDENTITY_POLICY_VERSION,
    IDENTITY_REGISTRY_VERSION,
)
from .text import SourceSpan, sha256_text

DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION = (
    "document-character-label-review-projection-v1"
)
LABEL_PROJECTION_POLICY_VERSION = "orthogonal-label-kind-stability-v1"
REVIEW_PROJECTION_POLICY_VERSION = "final-identity-graph-review-projection-v1"

LABEL_KINDS = (
    "proper_name",
    "alias",
    "title",
    "relationship_label",
    "descriptive_label",
    "unknown",
)
LABEL_STABILITIES = ("stable", "contextual", "temporary", "unknown")
SOURCE_LABEL_ROLES = (
    "name",
    "name_variant",
    "alias",
    "title",
    "contextual_description",
    "unknown",
)

_TITLE_SUFFIXES = (
    "战魂大师",
    "大师",
    "宗主",
    "长老",
    "陛下",
    "殿下",
    "教皇",
    "院长",
    "老师",
    "村长",
    "城主",
    "族长",
    "堂主",
    "阁主",
    "门主",
    "首领",
    "队长",
    "会长",
)
_RELATIONSHIP_SUFFIXES = (
    "爷爷",
    "奶奶",
    "父亲",
    "母亲",
    "爸爸",
    "妈妈",
    "哥哥",
    "姐姐",
    "弟弟",
    "妹妹",
    "叔叔",
    "阿姨",
    "伯伯",
    "姑姑",
    "舅舅",
    "师父",
    "师傅",
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


def _hex_string(value: object, label: str, *, length: int = 64) -> str:
    text = _string(value, label)
    if len(text) != length or any(character not in "0123456789abcdef" for character in text):
        raise ContractValidationError(f"{label} must be {length} lowercase hex characters")
    return text


def _span(value: object, label: str) -> SourceSpan:
    item = _mapping(value, label)
    if set(item) != {"start", "end"}:
        raise ContractValidationError(f"{label} must contain only start/end")
    return SourceSpan(
        _integer(item.get("start"), f"{label}.start"),
        _integer(item.get("end"), f"{label}.end"),
    )


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _order_independent_hash(value: object) -> str:
    def normalize(item: object) -> object:
        if isinstance(item, Mapping):
            return {str(key): normalize(member) for key, member in item.items()}
        if isinstance(item, list):
            members = [normalize(member) for member in item]
            return sorted(
                members,
                key=lambda member: json.dumps(
                    member,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        return item

    return _canonical_hash(normalize(value))


def _stable_id(prefix: str, payload: Mapping[str, object]) -> str:
    return f"{prefix}-{_canonical_hash(payload)[:20]}"


def _wrapped_ref_key(
    value: object,
    label: str,
    *,
    source_document_version_id: str,
) -> str:
    wrapped = _mapping(value, label)
    ref_type = _string(wrapped.get("ref_type"), f"{label}.ref_type")
    if ref_type == "local":
        if set(wrapped) != {"ref_type", "local_character_ref"}:
            raise ContractValidationError(f"{label} local wrapper fields are invalid")
        ref = _mapping(wrapped.get("local_character_ref"), f"{label}.local_character_ref")
        if set(ref) != {
            "source_document_version_id",
            "chunk_id",
            "local_mention_id",
            "mention_type",
            "packet_hash",
        }:
            raise ContractValidationError(f"{label} local character ref fields are invalid")
        if ref.get("mention_type") != "exact":
            raise ContractValidationError(f"{label} local mention_type must be exact")
        _string(ref.get("chunk_id"), f"{label}.chunk_id")
        _string(ref.get("local_mention_id"), f"{label}.local_mention_id")
        _hex_string(ref.get("packet_hash"), f"{label}.packet_hash")
    elif ref_type == "promoted":
        if set(wrapped) != {"ref_type", "promoted_character_ref"}:
            raise ContractValidationError(f"{label} promoted wrapper fields are invalid")
        ref = _mapping(
            wrapped.get("promoted_character_ref"),
            f"{label}.promoted_character_ref",
        )
        if set(ref) != {
            "source_document_version_id",
            "chunk_id",
            "source_local_mention_id",
            "source_mention_type",
            "promotion_index",
            "character_origin",
            "packet_hash",
            "promotion_hash",
        }:
            raise ContractValidationError(f"{label} promoted character ref fields are invalid")
        if ref.get("source_mention_type") != "describe":
            raise ContractValidationError(f"{label} promoted source mention must be describe")
        if ref.get("character_origin") != "remaining_describe":
            raise ContractValidationError(f"{label} promoted origin is invalid")
        if _integer(ref.get("promotion_index"), f"{label}.promotion_index") < 1:
            raise ContractValidationError(f"{label} promotion_index must be positive")
        _string(ref.get("chunk_id"), f"{label}.chunk_id")
        _string(ref.get("source_local_mention_id"), f"{label}.source_local_mention_id")
        _hex_string(ref.get("packet_hash"), f"{label}.packet_hash")
        _hex_string(ref.get("promotion_hash"), f"{label}.promotion_hash")
    else:
        raise ContractValidationError(f"{label}.ref_type is unsupported")
    if ref.get("source_document_version_id") != source_document_version_id:
        raise ContractValidationError(f"{label} refers to a different source document")
    return json.dumps(wrapped, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _classify_label(label_quote: str, source_label_role: str) -> tuple[str, str]:
    compact = "".join(character for character in label_quote if not character.isspace())
    if any(compact.endswith(suffix) for suffix in _RELATIONSHIP_SUFFIXES):
        return "relationship_label", "contextual"
    if source_label_role == "title" or any(
        compact.endswith(suffix) for suffix in _TITLE_SUFFIXES
    ):
        stability = (
            "stable"
            if source_label_role in {"name", "name_variant", "alias", "title"}
            else "contextual"
        )
        return "title", stability
    if source_label_role == "name":
        return "proper_name", "stable"
    if source_label_role in {"name_variant", "alias"}:
        return "alias", "stable"
    if source_label_role == "contextual_description":
        return "descriptive_label", "contextual"
    return "unknown", "unknown"


def _label_rank(label: Mapping[str, object], canonical_label: str) -> tuple[int, int, int, str]:
    kind_rank = {kind: index for index, kind in enumerate(LABEL_KINDS)}
    stability_rank = {stability: index for index, stability in enumerate(LABEL_STABILITIES)}
    return (
        kind_rank[str(label["label_kind"])],
        stability_rank[str(label["label_stability"])],
        0 if label["label_quote"] == canonical_label else 1,
        str(label["label_quote"]),
    )


def _validated_evidence(value: object, label: str) -> dict[str, object]:
    evidence = _mapping(value, label)
    if set(evidence) != {"evidence_quote", "document_span", "match_mode"}:
        raise ContractValidationError(f"{label} fields are invalid")
    _string(evidence.get("evidence_quote"), f"{label}.evidence_quote")
    _span(evidence.get("document_span"), f"{label}.document_span")
    if evidence.get("match_mode") not in {"exact", "whitespace_equivalent"}:
        raise ContractValidationError(f"{label}.match_mode is unsupported")
    return copy.deepcopy(dict(evidence))


def build_document_label_review_projection(
    *,
    document_text: str,
    registry: Mapping[str, object],
) -> dict[str, object]:
    """Project final label semantics and actionable reviews without mutating Registry."""
    if not isinstance(document_text, str) or not document_text:
        raise ContractValidationError("document_text must be a non-empty string")
    if registry.get("schema_version") != IDENTITY_REGISTRY_VERSION:
        raise ContractValidationError("registry schema_version is unsupported")
    if registry.get("identity_policy_version") != IDENTITY_POLICY_VERSION:
        raise ContractValidationError("registry identity_policy_version is unsupported")
    candidate_policy_version = _string(
        registry.get("candidate_policy_version"), "registry.candidate_policy_version"
    )
    if candidate_policy_version not in IDENTITY_COMPATIBLE_CANDIDATE_POLICY_VERSIONS:
        raise ContractValidationError("registry candidate_policy_version is unsupported")
    if registry.get("conflict_policy_version") != IDENTITY_CONFLICT_POLICY_VERSION:
        raise ContractValidationError("registry conflict_policy_version is unsupported")
    source_document_version_id = _string(
        registry.get("source_document_version_id"),
        "registry.source_document_version_id",
    )
    document_hash = _hex_string(registry.get("document_hash"), "registry.document_hash")
    if sha256_text(document_text) != document_hash:
        raise ContractValidationError("registry document_hash does not match source text")

    character_ids: set[str] = set()
    ref_owners: dict[str, str] = {}
    projected_characters: list[dict[str, object]] = []
    for character_index, raw_character in enumerate(
        _sequence(registry.get("characters"), "registry.characters")
    ):
        character_label = f"registry.characters[{character_index}]"
        character = _mapping(raw_character, character_label)
        if set(character) != {
            "character_id",
            "identity_status",
            "canonical_label",
            "canonical_label_status",
            "labels",
            "member_character_refs",
            "appearance_fact_refs",
            "possible_conflicts",
        }:
            raise ContractValidationError(f"{character_label} fields are invalid")
        character_id = _string(character.get("character_id"), f"{character_label}.character_id")
        if character_id in character_ids:
            raise ContractValidationError("registry contains duplicate character_id")
        character_ids.add(character_id)
        canonical_label = _string(
            character.get("canonical_label"), f"{character_label}.canonical_label"
        )
        canonical_label_status = _string(
            character.get("canonical_label_status"),
            f"{character_label}.canonical_label_status",
        )
        if canonical_label_status not in {"confirmed_name_like", "provisional_description"}:
            raise ContractValidationError("registry canonical_label_status is unsupported")
        if character.get("identity_status") not in {"linked", "singleton"}:
            raise ContractValidationError("registry identity_status is unsupported")

        projected_labels: list[dict[str, object]] = []
        seen_quotes: set[str] = set()
        for label_index, raw_label in enumerate(
            _sequence(character.get("labels"), f"{character_label}.labels")
        ):
            label_path = f"{character_label}.labels[{label_index}]"
            source_label = _mapping(raw_label, label_path)
            if set(source_label) != {"label_quote", "label_role", "globally_unique"}:
                raise ContractValidationError(f"{label_path} fields are invalid")
            label_quote = _string(source_label.get("label_quote"), f"{label_path}.label_quote")
            if label_quote in seen_quotes:
                raise ContractValidationError("character contains duplicate label_quote")
            seen_quotes.add(label_quote)
            source_label_role = _string(
                source_label.get("label_role"), f"{label_path}.label_role"
            )
            if source_label_role not in SOURCE_LABEL_ROLES:
                raise ContractValidationError("registry label_role is unsupported")
            if not isinstance(source_label.get("globally_unique"), bool):
                raise ContractValidationError("registry label globally_unique must be boolean")
            label_kind, label_stability = _classify_label(label_quote, source_label_role)
            projected_labels.append(
                {
                    "label_id": _stable_id(
                        "label",
                        {
                            "source_document_version_id": source_document_version_id,
                            "character_id": character_id,
                            "label_quote": label_quote,
                        },
                    ),
                    "label_quote": label_quote,
                    "source_label_role": source_label_role,
                    "label_kind": label_kind,
                    "label_stability": label_stability,
                    "source_globally_unique": source_label["globally_unique"],
                }
            )
        if not projected_labels or canonical_label not in seen_quotes:
            raise ContractValidationError("canonical label must appear exactly once in labels")
        preferred = min(projected_labels, key=lambda item: _label_rank(item, canonical_label))
        for item in projected_labels:
            item["selection_status"] = (
                "preferred" if item["label_id"] == preferred["label_id"] else "alternate"
            )
        projected_labels.sort(
            key=lambda item: (
                item["selection_status"] != "preferred",
                _label_rank(item, canonical_label),
                str(item["label_id"]),
            )
        )
        projected_characters.append(
            {
                "character_id": character_id,
                "source_canonical_label": canonical_label,
                "source_canonical_label_status": canonical_label_status,
                "preferred_label_id": preferred["label_id"],
                "labels": projected_labels,
            }
        )
        member_refs = _sequence(
            character.get("member_character_refs"),
            f"{character_label}.member_character_refs",
        )
        if not member_refs:
            raise ContractValidationError("registry character must own at least one member ref")
        for ref_index, member_ref in enumerate(member_refs):
            ref_key = _wrapped_ref_key(
                member_ref,
                f"{character_label}.member_character_refs[{ref_index}]",
                source_document_version_id=source_document_version_id,
            )
            if ref_key in ref_owners:
                raise ContractValidationError("local character ref belongs to multiple characters")
            ref_owners[ref_key] = character_id

    projected_characters.sort(key=lambda item: str(item["character_id"]))

    cannot_link_pairs: set[frozenset[str]] = set()
    for index, raw_constraint in enumerate(
        _sequence(registry.get("cannot_link_constraints"), "registry.cannot_link_constraints")
    ):
        label = f"registry.cannot_link_constraints[{index}]"
        constraint = _mapping(raw_constraint, label)
        if set(constraint) != {
            "left_node_key",
            "right_node_key",
            "left_character_id",
            "right_character_id",
            "grounded_identity_evidence",
        }:
            raise ContractValidationError(f"{label} fields are invalid")
        _hex_string(constraint.get("left_node_key"), f"{label}.left_node_key")
        _hex_string(constraint.get("right_node_key"), f"{label}.right_node_key")
        left_character_id = _string(
            constraint.get("left_character_id"), f"{label}.left_character_id"
        )
        right_character_id = _string(
            constraint.get("right_character_id"), f"{label}.right_character_id"
        )
        if (
            left_character_id not in character_ids
            or right_character_id not in character_ids
            or left_character_id == right_character_id
        ):
            raise ContractValidationError("cannot-link references invalid final characters")
        pair = frozenset({left_character_id, right_character_id})
        if pair in cannot_link_pairs:
            raise ContractValidationError("duplicate final-character cannot-link pair")
        cannot_link_pairs.add(pair)
        for evidence_index, evidence in enumerate(
            _sequence(
                constraint.get("grounded_identity_evidence"),
                f"{label}.grounded_identity_evidence",
            )
        ):
            _validated_evidence(evidence, f"{label}.grounded_identity_evidence[{evidence_index}]")

    reviews: dict[str, dict[str, object]] = {}
    review_subject_keys: dict[str, str] = {}
    for index, raw_review in enumerate(
        _sequence(registry.get("review_items"), "registry.review_items")
    ):
        label = f"registry.review_items[{index}]"
        review = _mapping(raw_review, label)
        if set(review) != {
            "review_item_id",
            "review_type",
            "subject_character_ref",
            "label_quote",
            "candidate_character_ids",
            "grounded_identity_evidence",
            "issue_codes",
            "status",
        }:
            raise ContractValidationError(f"{label} fields are invalid")
        review_id = _string(review.get("review_item_id"), f"{label}.review_item_id")
        if review_id in reviews:
            raise ContractValidationError("registry contains duplicate review_item_id")
        subject_key = _wrapped_ref_key(
            review.get("subject_character_ref"),
            f"{label}.subject_character_ref",
            source_document_version_id=source_document_version_id,
        )
        if subject_key not in ref_owners:
            raise ContractValidationError("review subject is not owned by a final character")
        candidate_ids = [
            _string(value, f"{label}.candidate_character_ids")
            for value in _sequence(
                review.get("candidate_character_ids"),
                f"{label}.candidate_character_ids",
            )
        ]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ContractValidationError("review contains duplicate candidate character ids")
        if any(candidate_id not in character_ids for candidate_id in candidate_ids):
            raise ContractValidationError("review references unknown candidate character")
        issue_codes = [
            _string(value, f"{label}.issue_codes")
            for value in _sequence(review.get("issue_codes"), f"{label}.issue_codes")
        ]
        if len(issue_codes) != len(set(issue_codes)):
            raise ContractValidationError("review contains duplicate issue codes")
        grounded_evidence = [
            _validated_evidence(value, f"{label}.grounded_identity_evidence[{evidence_index}]")
            for evidence_index, value in enumerate(
                _sequence(
                    review.get("grounded_identity_evidence"),
                    f"{label}.grounded_identity_evidence",
                )
            )
        ]
        grounded_evidence.sort(
            key=lambda item: (
                int(_mapping(item["document_span"], "evidence span")["start"]),
                int(_mapping(item["document_span"], "evidence span")["end"]),
                str(item["evidence_quote"]),
            )
        )
        reviews[review_id] = {
            "review_item_id": review_id,
            "review_type": _string(review.get("review_type"), f"{label}.review_type"),
            "subject_character_ref": copy.deepcopy(dict(_mapping(review["subject_character_ref"], label))),
            "subject_character_id": ref_owners[subject_key],
            "label_quote": _string(review.get("label_quote"), f"{label}.label_quote"),
            "candidate_character_ids": sorted(candidate_ids),
            "grounded_identity_evidence": grounded_evidence,
            "issue_codes": sorted(issue_codes),
            "source_status": _string(review.get("status"), f"{label}.status"),
        }
        review_subject_keys[review_id] = subject_key

    unresolved_by_review: dict[str, Mapping[str, object]] = {}
    for index, raw_unresolved in enumerate(
        _sequence(registry.get("unresolved_bindings"), "registry.unresolved_bindings")
    ):
        label = f"registry.unresolved_bindings[{index}]"
        unresolved = _mapping(raw_unresolved, label)
        if set(unresolved) != {
            "source_character_ref",
            "label_quote",
            "candidate_character_ids",
            "reason_code",
            "review_item_id",
        }:
            raise ContractValidationError(f"{label} fields are invalid")
        review_id = _string(unresolved.get("review_item_id"), f"{label}.review_item_id")
        if review_id not in reviews:
            raise ContractValidationError("unresolved binding references unknown review item")
        if review_id in unresolved_by_review:
            raise ContractValidationError("multiple unresolved bindings reference one review item")
        source_key = _wrapped_ref_key(
            unresolved.get("source_character_ref"),
            f"{label}.source_character_ref",
            source_document_version_id=source_document_version_id,
        )
        review = reviews[review_id]
        candidate_ids = [
            _string(value, f"{label}.candidate_character_ids")
            for value in _sequence(
                unresolved.get("candidate_character_ids"),
                f"{label}.candidate_character_ids",
            )
        ]
        if (
            source_key != review_subject_keys[review_id]
            or unresolved.get("label_quote") != review["label_quote"]
            or sorted(candidate_ids) != review["candidate_character_ids"]
            or unresolved.get("reason_code") != review["review_type"]
        ):
            raise ContractValidationError("unresolved binding does not match its review item")
        unresolved_by_review[review_id] = unresolved

    audit_items: list[dict[str, object]] = []
    actionable_items: list[dict[str, object]] = []
    for review_id, review in sorted(reviews.items()):
        subject_character_id = str(review["subject_character_id"])
        candidate_ids = [str(value) for value in review["candidate_character_ids"]]
        unresolved = unresolved_by_review.get(review_id)
        if unresolved is not None:
            current_status = "actionable"
            disposition = "actionable"
            resolution_reason = "final_graph_unresolved"
            reason_code = str(unresolved["reason_code"])
        elif subject_character_id in candidate_ids:
            current_status = "resolved"
            disposition = "audit_only"
            resolution_reason = "resolved_same_character"
            reason_code = str(review["review_type"])
        elif candidate_ids and all(
            frozenset({subject_character_id, candidate_id}) in cannot_link_pairs
            for candidate_id in candidate_ids
        ):
            current_status = "resolved"
            disposition = "audit_only"
            resolution_reason = "resolved_different_characters"
            reason_code = str(review["review_type"])
        else:
            current_status = "actionable"
            disposition = "actionable"
            resolution_reason = "not_closed_by_final_identity_graph"
            reason_code = str(review["review_type"])
        audit_item = {
            **review,
            "current_status": current_status,
            "disposition": disposition,
            "resolution_reason": resolution_reason,
        }
        audit_items.append(audit_item)
        if disposition == "actionable":
            actionable_items.append(
                {
                    "review_item_id": review_id,
                    "review_type": review["review_type"],
                    "subject_character_id": subject_character_id,
                    "label_quote": review["label_quote"],
                    "candidate_character_ids": candidate_ids,
                    "reason_code": reason_code,
                }
            )

    projected_labels = [
        label
        for character in projected_characters
        for label in character["labels"]
    ]
    kind_counts = {
        kind: sum(label["label_kind"] == kind for label in projected_labels)
        for kind in LABEL_KINDS
    }
    stability_counts = {
        stability: sum(label["label_stability"] == stability for label in projected_labels)
        for stability in LABEL_STABILITIES
    }
    result = {
        "schema_version": DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION,
        "label_projection_policy_version": LABEL_PROJECTION_POLICY_VERSION,
        "review_projection_policy_version": REVIEW_PROJECTION_POLICY_VERSION,
        "source_registry_version": IDENTITY_REGISTRY_VERSION,
        "source_registry_hash": _order_independent_hash(registry),
        "source_document_version_id": source_document_version_id,
        "document_hash": document_hash,
        "characters": projected_characters,
        "audit_items": audit_items,
        "actionable_review_items": actionable_items,
        "summary": {
            "characters": len(projected_characters),
            "labels": len(projected_labels),
            "preferred_labels": len(projected_characters),
            "proper_name_labels": kind_counts["proper_name"],
            "alias_labels": kind_counts["alias"],
            "title_labels": kind_counts["title"],
            "relationship_labels": kind_counts["relationship_label"],
            "descriptive_labels": kind_counts["descriptive_label"],
            "unknown_kind_labels": kind_counts["unknown"],
            "stable_labels": stability_counts["stable"],
            "contextual_labels": stability_counts["contextual"],
            "temporary_labels": stability_counts["temporary"],
            "unknown_stability_labels": stability_counts["unknown"],
            "audit_items": len(audit_items),
            "resolved_audit_items": sum(
                item["current_status"] == "resolved" for item in audit_items
            ),
            "actionable_review_items": len(actionable_items),
            "model_calls": 0,
            "complete": True,
        },
    }
    return result


def run_document_label_review_projection(
    *,
    document_text: str,
    registry_file: Path,
    output_file: Path,
) -> dict[str, object]:
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    projection = build_document_label_review_projection(
        document_text=document_text,
        registry=_mapping(registry, "registry"),
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(projection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return copy.deepcopy(dict(_mapping(projection["summary"], "projection.summary")))
