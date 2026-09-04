from __future__ import annotations

import copy

import pytest

from novel_character_generator.appearance_state_segments import (
    STATE_SEGMENT_POLICY_VERSION,
    attach_transition_ids,
    build_character_state_segments,
)
from novel_character_generator.appearance_transition import (
    APPEARANCE_TRANSITION_POLICY_VERSION,
    materialize_appearance_states,
)
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.text import sha256_text


SOURCE_VERSION = "source-state-segment-test"
CHARACTER_ID = "char-aaaaaaaaaaaaaaaaaaaa"
EMPTY_CHARACTER_ID = "char-bbbbbbbbbbbbbbbbbbbb"


def _span(text: str, quote: str) -> dict[str, int]:
    start = text.index(quote)
    return {"start": start, "end": start + len(quote)}


def _transition(
    text: str,
    *,
    evidence: str,
    dimension: str,
    attribute: str,
    before: str = "",
    after: str = "",
) -> dict[str, object]:
    return {
        "character_id": CHARACTER_ID,
        "evidence": evidence,
        "document_span": _span(text, evidence),
        "dimension": dimension,
        "attribute": attribute,
        "before": before,
        "after": after,
        "change": "change" if before and after else ("enter" if after else "exit"),
    }


def _inputs() -> tuple[
    str,
    list[dict[str, object]],
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    text = "唐三进入狼形。红眼。唐三换上新衣。蓝袍。\n平常。唐三长成青年。黑发。"
    chapters = [
        {
            "chapter_number": 1,
            "title": "测试",
            "document_span": {"start": 0, "end": len(text)},
        }
    ]
    facts = (
        ("cfact-00000000000000000001", "红眼", "face", "眼睛", "红色", "persistent_until_changed"),
        ("cfact-00000000000000000002", "蓝袍", "clothing", "衣服", "蓝袍", "scene"),
        ("cfact-00000000000000000003", "平常", "appearance_state", "状态", "平常", "momentary"),
        ("cfact-00000000000000000004", "黑发", "hair", "头发", "黑色", "stable"),
    )
    fact_groups = {
        "source_document_version_id": SOURCE_VERSION,
        "document_hash": sha256_text(text),
        "characters": [
            {"character_id": CHARACTER_ID, "canonical_fact_ids": [item[0] for item in facts]},
            {"character_id": EMPTY_CHARACTER_ID, "canonical_fact_ids": []},
        ],
        "fact_groups": [
            {
                "canonical_fact_id": canonical_fact_id,
                "character_id": CHARACTER_ID,
                "fact_quote": quote,
                "category": category,
                "attribute": attribute,
                "value": value,
                "document_fact_span": _span(text, quote),
            }
            for canonical_fact_id, quote, category, attribute, value, _ in facts
        ],
    }
    assignments = [
        {
            "canonical_fact_id": canonical_fact_id,
            "character_id": CHARACTER_ID,
            "chapter_number": 1,
            "order": order,
            "life": "unknown",
            "form": "unknown",
            "scene": "unknown",
            "persistence": persistence,
        }
        for order, (canonical_fact_id, _, _, _, _, persistence) in enumerate(facts)
    ]
    transitions = [
        _transition(
            text,
            evidence="唐三进入狼形",
            dimension="form",
            attribute="form_state",
            after="狼形",
        ),
        _transition(
            text,
            evidence="唐三换上新衣",
            dimension="scene",
            attribute="scene_state",
            after="新衣",
        ),
        _transition(
            text,
            evidence="唐三长成青年",
            dimension="life",
            attribute="life_stage",
            after="青年",
        ),
    ]
    return text, chapters, fact_groups, assignments, transitions


def _identified(text: str, transitions: list[dict[str, object]]) -> tuple[dict[str, object], ...]:
    return attach_transition_ids(
        document_text=text,
        source_document_version_id=SOURCE_VERSION,
        transition_policy_version=APPEARANCE_TRANSITION_POLICY_VERSION,
        transitions=transitions,
    )


def test_segments_are_deterministic_contiguous_and_bind_each_observation_once() -> None:
    text, chapters, fact_groups, assignments, transitions = _inputs()
    identified = _identified(text, transitions)
    first = build_character_state_segments(
        document_text=text,
        source_document_version_id=SOURCE_VERSION,
        chapters=chapters,
        fact_groups=fact_groups,
        fact_assignments=assignments,
        transitions=identified,
    )
    second = build_character_state_segments(
        document_text=text,
        source_document_version_id=SOURCE_VERSION,
        chapters=chapters,
        fact_groups=copy.deepcopy(fact_groups),
        fact_assignments=copy.deepcopy(assignments),
        transitions=copy.deepcopy(identified),
    )
    assert first == second

    character_segments = [item for item in first if item["character_id"] == CHARACTER_ID]
    assert character_segments[0]["document_span"]["start"] == 0
    assert character_segments[-1]["document_span"]["end"] == len(text)
    assert all(
        left["document_span"]["end"] == right["document_span"]["start"]
        for left, right in zip(character_segments, character_segments[1:])
    )
    observed = [fact_id for item in character_segments for fact_id in item["observed_fact_ids"]]
    assert sorted(observed) == sorted(item["canonical_fact_id"] for item in assignments)
    assert len(observed) == len(set(observed))

    by_fact = {
        fact_id: item
        for item in character_segments
        for fact_id in item["observed_fact_ids"]
    }
    assert by_fact["cfact-00000000000000000001"]["form"] == "狼形"
    assert by_fact["cfact-00000000000000000002"]["scene"] == "新衣"
    assert by_fact["cfact-00000000000000000003"]["scene"] == "unknown"
    assert by_fact["cfact-00000000000000000004"]["life"] == "青年"
    assert by_fact["cfact-00000000000000000004"]["form"] == "unknown"
    assert by_fact["cfact-00000000000000000004"]["scene"] == "unknown"

    empty_segments = [item for item in first if item["character_id"] == EMPTY_CHARACTER_ID]
    assert len(empty_segments) == 1
    assert empty_segments[0]["document_span"] == {"start": 0, "end": len(text)}
    assert empty_segments[0]["observed_fact_ids"] == []


def test_same_position_transitions_share_boundary_and_apply_in_dimension_order() -> None:
    text = "青年形态。"
    chapters = [{"document_span": {"start": 0, "end": len(text)}}]
    fact_groups = {
        "characters": [{"character_id": CHARACTER_ID, "canonical_fact_ids": []}],
        "fact_groups": [],
    }
    transitions = _identified(
        text,
        [
            _transition(
                text,
                evidence="青年形态",
                dimension="life",
                attribute="life_stage",
                after="青年",
            ),
            _transition(
                text,
                evidence="青年形态",
                dimension="form",
                attribute="form_state",
                after="青年",
            ),
        ],
    )
    segments = build_character_state_segments(
        document_text=text,
        source_document_version_id=SOURCE_VERSION,
        chapters=chapters,
        fact_groups=fact_groups,
        fact_assignments=[],
        transitions=transitions,
    )
    assert len(segments) == 1
    assert segments[0]["life"] == "青年"
    assert segments[0]["form"] == "青年"
    assert segments[0]["start_boundary"]["reasons"] == ["document_start", "transition"]
    assert segments[0]["start_boundary"]["transition_ids"] == sorted(
        item["transition_id"] for item in transitions
    )


def test_tampered_evidence_and_unknown_character_fail_closed() -> None:
    text, chapters, fact_groups, assignments, transitions = _inputs()
    tampered = copy.deepcopy(transitions)
    tampered[0]["evidence"] = "不存在的变化"
    with pytest.raises(ContractValidationError, match="does not replay"):
        _identified(text, tampered)

    ungrounded_state = copy.deepcopy(transitions)
    ungrounded_state[0]["after"] = "兽形"
    with pytest.raises(ContractValidationError, match="after state is not uniquely grounded"):
        _identified(text, ungrounded_state)

    wrong_id = dict(_identified(text, transitions)[0])
    wrong_id["transition_id"] = "transition-00000000000000000000"
    with pytest.raises(ContractValidationError, match="transition_id does not match"):
        _identified(text, [wrong_id])

    identified = list(_identified(text, transitions))
    identified[0]["character_id"] = "char-cccccccccccccccccccc"
    with pytest.raises(ContractValidationError, match="unknown character"):
        build_character_state_segments(
            document_text=text,
            source_document_version_id=SOURCE_VERSION,
            chapters=chapters,
            fact_groups=fact_groups,
            fact_assignments=assignments,
            transitions=identified,
        )


def test_materialized_state_artifact_contains_segments_and_derived_fact_state() -> None:
    text, chapters, fact_groups, assignments, transitions = _inputs()
    states = materialize_appearance_states(
        document_text=text,
        source_document_version_id=SOURCE_VERSION,
        scopes={"chapters": chapters, "fact_assignments": assignments},
        fact_groups=fact_groups,
        transitions=transitions,
        review=[],
        planned_chunks=1,
        model_calls=0,
    )
    assert states["schema_version"] == "document-character-appearance-states-v5"
    assert states["state_segment_policy_version"] == STATE_SEGMENT_POLICY_VERSION
    assert all(item["transition_id"].startswith("transition-") for item in states["transitions"])
    assert states["summary"]["characters_with_segments"] == 2
    assert states["summary"]["observed_fact_bindings"] == 4
    assert states["summary"]["relation_candidates"] == 0
    assert states["summary"]["normalized_propositions"] == 4
    assert states["summary"]["semantic_model_calls"] == 0
    assignments_by_id = {item["canonical_fact_id"]: item for item in states["fact_assignments"]}
    assert assignments_by_id["cfact-00000000000000000002"]["scene"] == "新衣"
    assert assignments_by_id["cfact-00000000000000000003"]["scene"] == "unknown"
    assert assignments_by_id["cfact-00000000000000000004"]["life"] == "青年"
    assert assignments_by_id["cfact-00000000000000000004"]["form"] == "unknown"
