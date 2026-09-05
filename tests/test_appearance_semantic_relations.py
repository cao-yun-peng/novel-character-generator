from __future__ import annotations

import copy

import pytest

from novel_character_generator.appearance_semantic_relations import (
    APPEARANCE_PROPOSITION_POLICY_VERSION,
    APPEARANCE_RELATION_POLICY_VERSION,
    build_appearance_semantic_projection,
    _classify_pair,
)
from novel_character_generator.errors import ContractValidationError


SOURCE_VERSION = "source-semantic-test"
CHARACTER_A = "char-aaaaaaaaaaaaaaaaaaaa"
CHARACTER_B = "char-bbbbbbbbbbbbbbbbbbbb"


@pytest.mark.parametrize("left,right", [
    ("高大", "不高大"), ("黑色", "不是黑色"), ("红润", "毫无红润"),
    ("苍白", "并非苍白"), ("苍老", "尚未苍老"), ("胡须", "没有胡须"),
    ("black", "not black"),
])
def test_negated_containment_is_not_compatible_in_either_direction(left, right):
    for a, b in ((left, right), (right, left)):
        assert _classify_pair(a, b)[0] == "unclassified"


def test_negated_fact_is_not_merged_or_promoted_to_conflict():
    groups, assignments, segments = _fixture()
    groups["fact_groups"][2]["value"] = "不高大"
    before = copy.deepcopy(groups)
    result = _build(groups, assignments, segments)
    related = [r for r in result["relations"]
               if "cfact-00000000000000000003" in (r["left_fact_id"], r["right_fact_id"])]
    assert all(r["relation"] == "unclassified" for r in related)
    assert groups == before
    assert result["summary"]["true_conflict_relations"] == 0
SEGMENT_A1 = "state-11111111111111111111"
SEGMENT_A2 = "state-22222222222222222222"
SEGMENT_B1 = "state-33333333333333333333"


def _fixture() -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    fact_specs = (
        ("cfact-00000000000000000001", CHARACTER_A, "body", "身材", "高大", 1, 3),
        ("cfact-00000000000000000002", CHARACTER_A, "body", "身材", "高大", 5, 7),
        ("cfact-00000000000000000003", CHARACTER_A, "body", "身材", "高大魁梧", 9, 13),
        ("cfact-00000000000000000004", CHARACTER_A, "body", "身材", "瘦小", 15, 17),
        ("cfact-00000000000000000005", CHARACTER_A, "hair", "头发颜色", "黑色", 20, 22),
        ("cfact-00000000000000000006", CHARACTER_A, "hair", "头发颜色", "白色", 55, 57),
        ("cfact-00000000000000000007", CHARACTER_B, "body", "身材", "高大", 25, 27),
    )
    fact_groups = {
        "source_document_version_id": SOURCE_VERSION,
        "characters": [
            {
                "character_id": CHARACTER_A,
                "canonical_fact_ids": [item[0] for item in fact_specs if item[1] == CHARACTER_A],
            },
            {
                "character_id": CHARACTER_B,
                "canonical_fact_ids": [item[0] for item in fact_specs if item[1] == CHARACTER_B],
            },
        ],
        "fact_groups": [
            {
                "canonical_fact_id": fact_id,
                "character_id": character_id,
                "category": category,
                "attribute": attribute,
                "value": value,
                "document_fact_span": {"start": start, "end": end},
            }
            for fact_id, character_id, category, attribute, value, start, end in fact_specs
        ],
    }
    assignments = [
        {
            "canonical_fact_id": fact_id,
            "character_id": character_id,
            "chapter_number": 1,
            "order": order,
            "life": "unknown",
            "form": "unknown",
            "scene": "unknown",
            "persistence": "unknown",
        }
        for order, (fact_id, character_id, _, _, _, _, _) in enumerate(fact_specs)
    ]
    state_segments = [
        {
            "state_segment_id": SEGMENT_A1,
            "character_id": CHARACTER_A,
            "sequence_index": 0,
            "document_span": {"start": 0, "end": 50},
            "life": "unknown",
            "form": "unknown",
            "scene": "unknown",
            "observed_fact_ids": [item[0] for item in fact_specs[:5]],
        },
        {
            "state_segment_id": SEGMENT_A2,
            "character_id": CHARACTER_A,
            "sequence_index": 1,
            "document_span": {"start": 50, "end": 100},
            "life": "unknown",
            "form": "unknown",
            "scene": "unknown",
            "observed_fact_ids": [fact_specs[5][0]],
        },
        {
            "state_segment_id": SEGMENT_B1,
            "character_id": CHARACTER_B,
            "sequence_index": 0,
            "document_span": {"start": 0, "end": 100},
            "life": "unknown",
            "form": "unknown",
            "scene": "unknown",
            "observed_fact_ids": [fact_specs[6][0]],
        },
    ]
    return fact_groups, assignments, state_segments


def _build(
    fact_groups: dict[str, object],
    assignments: list[dict[str, object]],
    state_segments: list[dict[str, object]],
) -> dict[str, object]:
    return build_appearance_semantic_projection(
        source_document_version_id=SOURCE_VERSION,
        document_length=100,
        fact_groups=fact_groups,
        fact_assignments=assignments,
        state_segments=state_segments,
    )


def test_relation_graph_precedes_and_limits_equivalent_component_normalization() -> None:
    fact_groups, assignments, state_segments = _fixture()
    result = _build(fact_groups, assignments, state_segments)
    assert result["relation_policy_version"] == APPEARANCE_RELATION_POLICY_VERSION
    assert result["normalization_policy_version"] == APPEARANCE_PROPOSITION_POLICY_VERSION
    assert result["summary"] == {
        "relation_candidates": 6,
        "equivalent_relations": 1,
        "compatible_relations": 2,
        "temporal_change_relations": 0,
        "state_change_relations": 0,
        "true_conflict_relations": 0,
        "unclassified_relations": 3,
        "normalized_propositions": 6,
        "semantic_model_calls": 0,
    }
    relations = {
        frozenset((item["left_fact_id"], item["right_fact_id"])): item
        for item in result["relations"]
    }
    equal_pair = relations[
        frozenset(("cfact-00000000000000000001", "cfact-00000000000000000002"))
    ]
    assert equal_pair["relation"] == "equivalent"
    assert equal_pair["direction"] == "symmetric"
    containment_pair = relations[
        frozenset(("cfact-00000000000000000001", "cfact-00000000000000000003"))
    ]
    assert containment_pair["relation"] == "compatible"
    assert containment_pair["direction"] == "right_contains_left"
    unrelated_pair = relations[
        frozenset(("cfact-00000000000000000001", "cfact-00000000000000000004"))
    ]
    assert unrelated_pair["relation"] == "unclassified"

    merged = next(
        item
        for item in result["normalized_propositions"]
        if item["member_fact_ids"]
        == ["cfact-00000000000000000001", "cfact-00000000000000000002"]
    )
    assert merged["normalization_basis"] == "equivalent_component"
    assert merged["normalized_value"] == "高大"
    assert all(
        "cfact-00000000000000000003" not in item["member_fact_ids"]
        or len(item["member_fact_ids"]) == 1
        for item in result["normalized_propositions"]
    )


def test_different_segment_attribute_or_character_does_not_create_relation() -> None:
    fact_groups, assignments, state_segments = _fixture()
    relations = _build(fact_groups, assignments, state_segments)["relations"]
    related_pairs = {
        frozenset((item["left_fact_id"], item["right_fact_id"])) for item in relations
    }
    assert frozenset(("cfact-00000000000000000005", "cfact-00000000000000000006")) not in related_pairs
    assert frozenset(("cfact-00000000000000000001", "cfact-00000000000000000007")) not in related_pairs
    assert all(item["attribute"] == "身材" for item in relations)


def test_projection_is_stable_under_input_array_reordering() -> None:
    fact_groups, assignments, state_segments = _fixture()
    first = _build(fact_groups, assignments, state_segments)
    reordered_groups = copy.deepcopy(fact_groups)
    reordered_groups["characters"].reverse()
    for character in reordered_groups["characters"]:
        character["canonical_fact_ids"].reverse()
    reordered_groups["fact_groups"].reverse()
    reordered_assignments = list(reversed(copy.deepcopy(assignments)))
    reordered_segments = list(reversed(copy.deepcopy(state_segments)))
    for segment in reordered_segments:
        segment["observed_fact_ids"].reverse()
    assert _build(reordered_groups, reordered_assignments, reordered_segments) == first


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_observation", "multiple segments"),
        ("assignment_state", "state does not match"),
        ("fact_outside_segment", "starts outside"),
    ],
)
def test_projection_fails_closed_on_stale_or_ambiguous_state_inputs(
    mutation: str,
    message: str,
) -> None:
    fact_groups, assignments, state_segments = _fixture()
    if mutation == "duplicate_observation":
        state_segments[1]["observed_fact_ids"].append("cfact-00000000000000000001")
    elif mutation == "assignment_state":
        assignments[0]["life"] = "adult"
    else:
        fact_groups["fact_groups"][0]["document_fact_span"] = {"start": 60, "end": 62}
    with pytest.raises(ContractValidationError, match=message):
        _build(fact_groups, assignments, state_segments)
