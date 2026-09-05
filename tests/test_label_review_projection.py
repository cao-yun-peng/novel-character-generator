from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from novel_character_generator.errors import ContractValidationError
from novel_character_generator.identity import (
    IDENTITY_CANDIDATE_POLICY_VERSION,
    IDENTITY_CONFLICT_POLICY_VERSION,
    IDENTITY_POLICY_VERSION,
    IDENTITY_REGISTRY_VERSION,
)
from novel_character_generator.label_review_projection import (
    DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION,
    LABEL_PROJECTION_POLICY_VERSION,
    REVIEW_PROJECTION_POLICY_VERSION,
    build_document_label_review_projection,
    run_document_label_review_projection,
)
from novel_character_generator.text import sha256_text


SOURCE_VERSION = "source-label-review-test"
CHARACTER_TANGSAN = "char-11111111111111111111"
CHARACTER_MASTER = "char-22222222222222222222"
CHARACTER_GUARD = "char-33333333333333333333"


def _local_ref(local_id: str, fill: str) -> dict[str, object]:
    return {
        "ref_type": "local",
        "local_character_ref": {
            "source_document_version_id": SOURCE_VERSION,
            "chunk_id": "chunk-1",
            "local_mention_id": local_id,
            "mention_type": "exact",
            "packet_hash": fill * 64,
        },
    }


def _promoted_ref() -> dict[str, object]:
    return {
        "ref_type": "promoted",
        "promoted_character_ref": {
            "source_document_version_id": SOURCE_VERSION,
            "chunk_id": "chunk-1",
            "source_local_mention_id": "m3",
            "source_mention_type": "describe",
            "promotion_index": 1,
            "character_origin": "remaining_describe",
            "packet_hash": "3" * 64,
            "promotion_hash": "4" * 64,
        },
    }


def _character(
    character_id: str,
    canonical_label: str,
    canonical_label_status: str,
    labels: list[tuple[str, str, bool]],
    member_ref: dict[str, object],
) -> dict[str, object]:
    return {
        "character_id": character_id,
        "identity_status": "singleton",
        "canonical_label": canonical_label,
        "canonical_label_status": canonical_label_status,
        "labels": [
            {
                "label_quote": quote,
                "label_role": role,
                "globally_unique": globally_unique,
            }
            for quote, role, globally_unique in labels
        ],
        "member_character_refs": [member_ref],
        "appearance_fact_refs": [],
        "possible_conflicts": [],
    }


def _review(
    review_id: str,
    review_type: str,
    subject_ref: dict[str, object],
    label_quote: str,
    candidate_ids: list[str],
) -> dict[str, object]:
    return {
        "review_item_id": review_id,
        "review_type": review_type,
        "subject_character_ref": subject_ref,
        "label_quote": label_quote,
        "candidate_character_ids": candidate_ids,
        "grounded_identity_evidence": [],
        "issue_codes": [],
        "status": "pending",
    }


def _fixture() -> tuple[str, dict[str, object]]:
    text = "唐三见到大师和看门的青年。"
    tangsan_ref = _local_ref("m1", "1")
    master_ref = _local_ref("m2", "2")
    guard_ref = _promoted_ref()
    resolved_same = _review(
        "review-same",
        "partial_identity_evidence_grounding",
        tangsan_ref,
        "唐三",
        [CHARACTER_TANGSAN],
    )
    resolved_different = _review(
        "review-different",
        "insufficient_identity_evidence",
        master_ref,
        "大师",
        [CHARACTER_TANGSAN],
    )
    actionable = _review(
        "review-actionable",
        "insufficient_identity_evidence",
        guard_ref,
        "看门的青年",
        [CHARACTER_MASTER],
    )
    registry = {
        "schema_version": IDENTITY_REGISTRY_VERSION,
        "identity_policy_version": IDENTITY_POLICY_VERSION,
        "candidate_policy_version": IDENTITY_CANDIDATE_POLICY_VERSION,
        "conflict_policy_version": IDENTITY_CONFLICT_POLICY_VERSION,
        "source_document_version_id": SOURCE_VERSION,
        "document_hash": sha256_text(text),
        "characters": [
            _character(
                CHARACTER_TANGSAN,
                "唐三",
                "confirmed_name_like",
                [("唐三", "name", True), ("小三", "name_variant", True)],
                tangsan_ref,
            ),
            _character(
                CHARACTER_MASTER,
                "大师",
                "confirmed_name_like",
                [("大师", "name", True), ("这位村长", "contextual_description", False)],
                master_ref,
            ),
            _character(
                CHARACTER_GUARD,
                "看门的青年",
                "provisional_description",
                [("看门的青年", "contextual_description", False)],
                guard_ref,
            ),
        ],
        "unresolved_bindings": [
            {
                "source_character_ref": guard_ref,
                "label_quote": "看门的青年",
                "candidate_character_ids": [CHARACTER_MASTER],
                "reason_code": "insufficient_identity_evidence",
                "review_item_id": "review-actionable",
            }
        ],
        "review_items": [resolved_same, resolved_different, actionable],
        "cannot_link_constraints": [
            {
                "left_node_key": "a" * 64,
                "right_node_key": "b" * 64,
                "left_character_id": CHARACTER_MASTER,
                "right_character_id": CHARACTER_TANGSAN,
                "grounded_identity_evidence": [],
            }
        ],
        "summary": {},
    }
    return text, registry


def _build() -> dict[str, object]:
    text, registry = _fixture()
    return build_document_label_review_projection(document_text=text, registry=registry)


def test_projects_orthogonal_label_semantics_and_preferred_labels() -> None:
    result = _build()
    assert result["schema_version"] == DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION
    assert result["label_projection_policy_version"] == LABEL_PROJECTION_POLICY_VERSION
    assert result["review_projection_policy_version"] == REVIEW_PROJECTION_POLICY_VERSION
    characters = {item["character_id"]: item for item in result["characters"]}
    tangsan = characters[CHARACTER_TANGSAN]
    tangsan_labels = {item["label_quote"]: item for item in tangsan["labels"]}
    assert tangsan_labels["唐三"]["label_kind"] == "proper_name"
    assert tangsan_labels["唐三"]["label_stability"] == "stable"
    assert tangsan_labels["小三"]["label_kind"] == "alias"
    assert tangsan_labels["唐三"]["selection_status"] == "preferred"

    master_labels = {
        item["label_quote"]: item for item in characters[CHARACTER_MASTER]["labels"]
    }
    assert master_labels["大师"]["source_label_role"] == "name"
    assert master_labels["大师"]["source_globally_unique"] is True
    assert master_labels["大师"]["label_kind"] == "title"
    assert master_labels["大师"]["label_stability"] == "stable"
    assert master_labels["这位村长"]["label_kind"] == "title"
    assert master_labels["这位村长"]["label_stability"] == "contextual"

    guard = characters[CHARACTER_GUARD]["labels"][0]
    assert guard["label_kind"] == "descriptive_label"
    assert guard["label_stability"] == "contextual"


def test_preserves_all_audit_items_but_only_surfaces_open_work() -> None:
    result = _build()
    audit = {item["review_item_id"]: item for item in result["audit_items"]}
    assert len(audit) == 3
    assert audit["review-same"]["source_status"] == "pending"
    assert audit["review-same"]["current_status"] == "resolved"
    assert audit["review-same"]["resolution_reason"] == "resolved_same_character"
    assert audit["review-different"]["current_status"] == "resolved"
    assert (
        audit["review-different"]["resolution_reason"]
        == "resolved_different_characters"
    )
    assert audit["review-actionable"]["disposition"] == "actionable"
    assert result["actionable_review_items"] == [
        {
            "review_item_id": "review-actionable",
            "review_type": "insufficient_identity_evidence",
            "subject_character_id": CHARACTER_GUARD,
            "label_quote": "看门的青年",
            "candidate_character_ids": [CHARACTER_MASTER],
            "reason_code": "insufficient_identity_evidence",
        }
    ]
    assert result["summary"]["resolved_audit_items"] == 2
    assert result["summary"]["actionable_review_items"] == 1
    assert result["summary"]["model_calls"] == 0


def test_projection_is_stable_under_registry_array_reordering() -> None:
    text, registry = _fixture()
    first = build_document_label_review_projection(document_text=text, registry=registry)
    reordered = copy.deepcopy(registry)
    reordered["characters"].reverse()
    reordered["review_items"].reverse()
    reordered["cannot_link_constraints"].reverse()
    for character in reordered["characters"]:
        character["labels"].reverse()
        character["member_character_refs"].reverse()
    assert build_document_label_review_projection(
        document_text=text,
        registry=reordered,
    ) == first


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_review", "duplicate review_item_id"),
        ("unknown_review", "unknown review item"),
        ("unknown_subject", "not owned by a final character"),
        ("mismatched_unresolved", "does not match its review item"),
    ],
)
def test_projection_fails_closed_on_stale_review_graph(
    mutation: str,
    message: str,
) -> None:
    text, registry = _fixture()
    if mutation == "duplicate_review":
        registry["review_items"].append(copy.deepcopy(registry["review_items"][0]))
    elif mutation == "unknown_review":
        registry["unresolved_bindings"][0]["review_item_id"] = "review-missing"
    elif mutation == "unknown_subject":
        registry["review_items"][0]["subject_character_ref"] = _local_ref("m9", "9")
    else:
        registry["unresolved_bindings"][0]["candidate_character_ids"] = [CHARACTER_TANGSAN]
    with pytest.raises(ContractValidationError, match=message):
        build_document_label_review_projection(document_text=text, registry=registry)


def test_run_writes_projection_and_returns_summary(tmp_path: Path) -> None:
    text, registry = _fixture()
    registry_file = tmp_path / "registry.json"
    output_file = tmp_path / "projection" / "labels-review.json"
    registry_file.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    summary = run_document_label_review_projection(
        document_text=text,
        registry_file=registry_file,
        output_file=output_file,
    )
    written = json.loads(output_file.read_text(encoding="utf-8"))
    assert written["summary"] == summary
    assert summary["complete"] is True
