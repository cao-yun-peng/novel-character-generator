from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from novel_character_generator.appearance_scope import (
    build_document_character_appearance_scopes,
)
from novel_character_generator.appearance_transition import materialize_appearance_states
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.fact_groups import (
    DOCUMENT_CHARACTER_FACT_GROUPS_VERSION,
    POST_LINK_FACT_GROUPING_POLICY_VERSION,
)
from novel_character_generator.identity import IDENTITY_REGISTRY_VERSION
from novel_character_generator.label_review_projection import (
    DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION,
    LABEL_PROJECTION_POLICY_VERSION,
    REVIEW_PROJECTION_POLICY_VERSION,
)
from novel_character_generator.render_profile_compiler import (
    FACT_APPLICABILITY_POLICY_VERSION,
    RENDER_PROFILE_COMPILER_POLICY_VERSION,
    RENDER_PROFILE_REQUESTS_VERSION,
    RENDER_READY_CHARACTER_PROFILES_VERSION,
    _project_relation_outcomes,
    build_render_ready_character_profiles,
    run_render_ready_character_profiles,
)
from novel_character_generator.text import sha256_text


SOURCE_VERSION = "render-compiler-test-source"
CHARACTER_A = "char-aaaaaaaaaaaaaaaaaaaa"
CHARACTER_B = "char-bbbbbbbbbbbbbbbbbbbb"


def _span(text: str, quote: str) -> dict[str, int]:
    start = text.index(quote)
    return {"start": start, "end": start + len(quote)}


def _fact(
    text: str,
    *,
    fact_id: str,
    character_id: str,
    quote: str,
    category: str,
    attribute: str,
    value: str,
) -> dict[str, object]:
    document_span = _span(text, quote)
    source_fact_hash = sha256_text(f"source:{fact_id}")
    return {
        "canonical_fact_id": fact_id,
        "character_id": character_id,
        "fact_quote": quote,
        "category": category,
        "attribute": attribute,
        "value": value,
        "document_fact_span": document_span,
        "source_fact_hashes": [source_fact_hash],
        "source_occurrences": [
            {
                "source_fact_hash": source_fact_hash,
                "source_occurrence_index": 0,
                "source_occurrence": {
                    "chunk_id": "chunk-test",
                    "chunk_hash": sha256_text(text),
                    "chunk_source_span": {"start": 0, "end": len(text)},
                    "source_character_ref": {
                        "source_document_version_id": SOURCE_VERSION,
                        "chunk_id": "chunk-test",
                    },
                    "source_mention_id": "m1",
                    "source_mention_type": "exact",
                    "source_evidence_quote": quote,
                    "chunk_evidence_span": document_span,
                    "document_evidence_span": document_span,
                    "chunk_fact_span": document_span,
                    "match_mode": "exact",
                },
            }
        ],
        "grouping_reason": "same_character_span_category_attribute_value",
        "scope_assignment_status": "unassigned",
    }


def _label_character(
    character_id: str,
    label_id: str,
    name: str,
) -> dict[str, object]:
    return {
        "character_id": character_id,
        "source_canonical_label": name,
        "source_canonical_label_status": "confirmed_name_like",
        "preferred_label_id": label_id,
        "labels": [
            {
                "label_id": label_id,
                "label_quote": name,
                "source_label_role": "name",
                "label_kind": "proper_name",
                "label_stability": "stable",
                "source_globally_unique": True,
                "selection_status": "preferred",
            }
        ],
    }


def _fixture() -> tuple[str, dict[str, object], dict[str, object], dict[str, object]]:
    text = (
        "第一章 起点\n"
        "二十九岁，穿着旧衣。\n"
        "蜕变成孩子。\n"
        "孩子身形幼小，脸色苍白。\n"
        "第二章 狼\n"
        "素云涛平常俊朗，胸前有徽记。\n"
        "独狼，附体。\n"
        "头发变成灰色。\n"
        "肌肉膨胀。\n"
        "收回武魂附体。\n"
    )
    facts = [
        _fact(
            text,
            fact_id="cfact-11111111111111111111",
            character_id=CHARACTER_A,
            quote="二十九岁",
            category="age",
            attribute="年龄",
            value="二十九岁",
        ),
        _fact(
            text,
            fact_id="cfact-22222222222222222222",
            character_id=CHARACTER_A,
            quote="旧衣",
            category="clothing",
            attribute="服装",
            value="旧衣",
        ),
        _fact(
            text,
            fact_id="cfact-33333333333333333333",
            character_id=CHARACTER_A,
            quote="身形幼小",
            category="body",
            attribute="身形",
            value="幼小",
        ),
        _fact(
            text,
            fact_id="cfact-44444444444444444444",
            character_id=CHARACTER_A,
            quote="脸色苍白",
            category="appearance_state",
            attribute="脸色",
            value="苍白",
        ),
        _fact(
            text,
            fact_id="cfact-55555555555555555555",
            character_id=CHARACTER_B,
            quote="俊朗",
            category="face",
            attribute="相貌",
            value="俊朗",
        ),
        _fact(
            text,
            fact_id="cfact-66666666666666666666",
            character_id=CHARACTER_B,
            quote="徽记",
            category="distinctive_mark",
            attribute="胸前标记",
            value="徽记",
        ),
        _fact(
            text,
            fact_id="cfact-77777777777777777777",
            character_id=CHARACTER_B,
            quote="头发变成灰色",
            category="hair",
            attribute="发色",
            value="灰色",
        ),
        _fact(
            text,
            fact_id="cfact-88888888888888888888",
            character_id=CHARACTER_B,
            quote="肌肉膨胀",
            category="body",
            attribute="体型",
            value="膨胀",
        ),
    ]
    fact_groups = {
        "schema_version": DOCUMENT_CHARACTER_FACT_GROUPS_VERSION,
        "grouping_policy_version": POST_LINK_FACT_GROUPING_POLICY_VERSION,
        "source_document_version_id": SOURCE_VERSION,
        "document_hash": sha256_text(text),
        "coverage_status": "complete",
        "processed_source_end": len(text),
        "source_artifacts": {},
        "characters": [
            {
                "character_id": CHARACTER_A,
                "identity_status": "linked",
                "canonical_label": "唐三",
                "canonical_fact_ids": [
                    fact["canonical_fact_id"]
                    for fact in facts
                    if fact["character_id"] == CHARACTER_A
                ],
            },
            {
                "character_id": CHARACTER_B,
                "identity_status": "linked",
                "canonical_label": "素云涛",
                "canonical_fact_ids": [
                    fact["canonical_fact_id"]
                    for fact in facts
                    if fact["character_id"] == CHARACTER_B
                ],
            },
        ],
        "fact_groups": facts,
        "unassigned_source_fact_hashes": [],
        "unassigned_source_occurrences": [],
        "summary": {"canonical_fact_groups": len(facts)},
    }
    scopes = build_document_character_appearance_scopes(
        document_text=text,
        fact_groups=fact_groups,
    )
    transitions = [
        {
            "character_id": CHARACTER_A,
            "evidence": "蜕变成孩子",
            "document_span": _span(text, "蜕变成孩子"),
            "dimension": "life",
            "attribute": "life_stage",
            "before": "",
            "after": "孩子",
            "change": "enter",
        },
        {
            "character_id": CHARACTER_B,
            "evidence": "独狼，附体",
            "document_span": _span(text, "独狼，附体"),
            "dimension": "form",
            "attribute": "form_state",
            "before": "",
            "after": "独狼，附体",
            "change": "enter",
        },
        {
            "character_id": CHARACTER_B,
            "evidence": "头发变成灰色",
            "document_span": _span(text, "头发变成灰色"),
            "dimension": "appearance",
            "attribute": "发色",
            "before": "头发",
            "after": "灰色",
            "change": "change",
        },
        {
            "character_id": CHARACTER_B,
            "evidence": "肌肉膨胀",
            "document_span": _span(text, "肌肉膨胀"),
            "dimension": "appearance",
            "attribute": "体型",
            "before": "肌肉",
            "after": "膨胀",
            "change": "change",
        },
        {
            "character_id": CHARACTER_B,
            "evidence": "收回武魂附体",
            "document_span": _span(text, "收回武魂附体"),
            "dimension": "form",
            "attribute": "form_state",
            "before": "武魂附体",
            "after": "",
            "change": "exit",
        },
    ]
    appearance_states = materialize_appearance_states(
        document_text=text,
        source_document_version_id=SOURCE_VERSION,
        scopes=scopes,
        fact_groups=fact_groups,
        transitions=transitions,
        review=[],
        planned_chunks=1,
        model_calls=0,
    )
    label_projection = {
        "schema_version": DOCUMENT_LABEL_REVIEW_PROJECTION_VERSION,
        "label_projection_policy_version": LABEL_PROJECTION_POLICY_VERSION,
        "review_projection_policy_version": REVIEW_PROJECTION_POLICY_VERSION,
        "source_registry_version": IDENTITY_REGISTRY_VERSION,
        "source_registry_hash": "a" * 64,
        "source_document_version_id": SOURCE_VERSION,
        "document_hash": sha256_text(text),
        "characters": [
            _label_character(CHARACTER_A, "label-11111111111111111111", "唐三"),
            _label_character(CHARACTER_B, "label-22222222222222222222", "素云涛"),
        ],
        "audit_items": [],
        "actionable_review_items": [],
        "summary": {},
    }
    return text, fact_groups, appearance_states, label_projection


def _request(
    character_id: str,
    *,
    life: str | None,
    form: str | None,
    scene: str | None,
    position: int | None,
) -> dict[str, object]:
    return {
        "character_id": character_id,
        "selector": {
            "life_stage": life,
            "form_state": form,
            "scene_state": scene,
            "document_position": position,
        },
    }


def _build(requests: list[dict[str, object]]) -> dict[str, object]:
    text, fact_groups, states, labels = _fixture()
    return build_render_ready_character_profiles(
        document_text=text,
        fact_groups=fact_groups,
        appearance_states=states,
        label_projection=labels,
        requests=requests,
    )


def test_compiles_four_state_cards_without_cross_state_or_future_mixing() -> None:
    text, _, _, _ = _fixture()
    pre_position = text.index("旧衣") + len("旧衣")
    child_position = text.index("脸色苍白")
    normal_position = text.index("徽记") + len("徽记")
    wolf_position = text.index("肌肉膨胀") + len("肌肉膨胀")
    result = _build(
        [
            _request(CHARACTER_A, life="unknown", form="unknown", scene="unknown", position=pre_position),
            _request(CHARACTER_A, life="孩子", form="unknown", scene="unknown", position=child_position),
            _request(CHARACTER_B, life="unknown", form="unknown", scene="unknown", position=normal_position),
            _request(CHARACTER_B, life="unknown", form="独狼，附体", scene="unknown", position=wolf_position),
        ]
    )
    assert result["schema_version"] == RENDER_READY_CHARACTER_PROFILES_VERSION
    assert result["compiler_policy_version"] == RENDER_PROFILE_COMPILER_POLICY_VERSION
    assert result["applicability_policy_version"] == FACT_APPLICABILITY_POLICY_VERSION
    assert result["summary"]["compiled_profiles"] == 4
    profiles = {item["selector"]["document_position"]: item for item in result["profiles"]}

    pre = profiles[pre_position]
    assert pre["identity_labels"]["character_id"] == CHARACTER_A
    assert "cfact-11111111111111111111" in pre["active_fact_ids"]
    assert "cfact-33333333333333333333" not in pre["active_fact_ids"] + pre["provisional_fact_ids"]

    child = profiles[child_position]
    assert "cfact-11111111111111111111" not in child["active_fact_ids"] + child["provisional_fact_ids"]
    assert "cfact-33333333333333333333" in child["active_fact_ids"] + child["provisional_fact_ids"]

    normal = profiles[normal_position]
    assert "cfact-66666666666666666666" in normal["active_fact_ids"]
    assert "cfact-77777777777777777777" not in normal["active_fact_ids"] + normal["provisional_fact_ids"]

    wolf = profiles[wolf_position]
    assert "cfact-55555555555555555555" not in wolf["active_fact_ids"] + wolf["provisional_fact_ids"]
    assert "cfact-77777777777777777777" in wolf["provisional_fact_ids"]
    assert "cfact-88888888888888888888" in wolf["provisional_fact_ids"]
    assert [item["dimension"] for item in wolf["transitions"]] == [
        "form",
        "appearance",
        "appearance",
    ]
    assert result["summary"]["model_calls"] == 0


def test_selector_required_and_no_match_never_mix_traits() -> None:
    text, _, _, _ = _fixture()
    result = _build(
        [
            _request(CHARACTER_B, life="unknown", form="独狼，附体", scene="unknown", position=None),
            _request(
                CHARACTER_B,
                life="unknown",
                form="独狼，附体",
                scene="unknown",
                position=text.index("俊朗"),
            ),
        ]
    )
    statuses = {item["compile_status"]: item for item in result["profiles"]}
    assert set(statuses) == {"selector_required", "no_matching_state"}
    for profile in statuses.values():
        assert profile["selected_state_segment_id"] is None
        assert profile["stable_traits"] == []
        assert profile["variant_traits"] == []
        assert profile["scene_overrides"] == []


def test_momentary_and_unknown_persistence_are_not_silently_stable() -> None:
    text, _, _, _ = _fixture()
    at_moment = _build(
        [
            _request(
                CHARACTER_A,
                life="孩子",
                form="unknown",
                scene="unknown",
                position=text.index("脸色苍白"),
            )
        ]
    )["profiles"][0]
    assert "cfact-44444444444444444444" in at_moment["active_fact_ids"]
    assert any(
        item["canonical_fact_ids"] == ["cfact-44444444444444444444"]
        for item in at_moment["scene_overrides"]
    )

    later = _build(
        [
            _request(
                CHARACTER_A,
                life="孩子",
                form="unknown",
                scene="unknown",
                position=text.index("第二章"),
            )
        ]
    )["profiles"][0]
    assert "cfact-44444444444444444444" not in later["active_fact_ids"]
    assert "cfact-44444444444444444444" not in later["provisional_fact_ids"]
    assert "cfact-33333333333333333333" in later["provisional_fact_ids"]
    assert any(
        item["code"] == "provisional_fact_applicability"
        for item in later["compile_warnings"]
    )


def test_true_conflict_requires_two_active_facts_and_unclassified_stays_warning() -> None:
    relation = {
        "relation_id": "relation-11111111111111111111",
        "character_id": CHARACTER_A,
        "state_segment_id": "state-11111111111111111111",
        "attribute": "年龄",
        "left_fact_id": "cfact-11111111111111111111",
        "right_fact_id": "cfact-22222222222222222222",
        "relation": "true_conflict",
        "direction": "symmetric",
        "rule": "no_safe_deterministic_rule",
    }
    included = {
        "cfact-11111111111111111111",
        "cfact-22222222222222222222",
    }
    active = {
        fact_id: ("active", "test")
        for fact_id in included
    }
    conflicts, warnings = _project_relation_outcomes(
        relations=[relation],
        included_fact_ids=included,
        applicability=active,
    )
    assert len(conflicts) == 1
    assert conflicts[0]["applicability_status"] == "active_overlap"
    assert warnings == []

    provisional = dict(active)
    provisional["cfact-22222222222222222222"] = ("provisional", "test")
    conflicts, warnings = _project_relation_outcomes(
        relations=[relation],
        included_fact_ids=included,
        applicability=provisional,
    )
    assert conflicts == []
    assert [item["code"] for item in warnings] == [
        "provisional_true_conflict_overlap"
    ]

    unclassified = {**relation, "relation": "unclassified"}
    conflicts, warnings = _project_relation_outcomes(
        relations=[unclassified],
        included_fact_ids=included,
        applicability=active,
    )
    assert conflicts == []
    assert [item["code"] for item in warnings] == [
        "active_unclassified_relation"
    ]


def test_output_is_stable_under_source_and_request_array_reordering() -> None:
    text, fact_groups, states, labels = _fixture()
    requests = [
        _request(CHARACTER_A, life="孩子", form="unknown", scene="unknown", position=text.index("第二章")),
        _request(CHARACTER_B, life="unknown", form="独狼，附体", scene="unknown", position=text.index("肌肉膨胀")),
    ]
    first = build_render_ready_character_profiles(
        document_text=text,
        fact_groups=fact_groups,
        appearance_states=states,
        label_projection=labels,
        requests=requests,
    )
    reordered_fact_groups = copy.deepcopy(fact_groups)
    reordered_states = copy.deepcopy(states)
    reordered_labels = copy.deepcopy(labels)
    reordered_fact_groups["characters"].reverse()
    reordered_fact_groups["fact_groups"].reverse()
    for character in reordered_fact_groups["characters"]:
        character["canonical_fact_ids"].reverse()
    reordered_states["transitions"].reverse()
    reordered_states["state_segments"].reverse()
    reordered_states["relations"].reverse()
    reordered_states["normalized_propositions"].reverse()
    reordered_states["fact_assignments"].reverse()
    reordered_labels["characters"].reverse()
    second = build_render_ready_character_profiles(
        document_text=text,
        fact_groups=reordered_fact_groups,
        appearance_states=reordered_states,
        label_projection=reordered_labels,
        requests=list(reversed(requests)),
    )
    assert second == first


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("fact_span", "canonical fact quote does not replay"),
        ("state_segment", "state segments are not reproducible"),
        ("label_character", "character rosters differ"),
        ("unknown_request", "unknown character"),
    ],
)
def test_fails_closed_on_stale_cross_layer_references(source: str, message: str) -> None:
    text, fact_groups, states, labels = _fixture()
    request = _request(
        CHARACTER_A,
        life="孩子",
        form="unknown",
        scene="unknown",
        position=text.index("身形幼小"),
    )
    if source == "fact_span":
        fact_groups["fact_groups"][0]["document_fact_span"]["start"] += 1
    elif source == "state_segment":
        states["state_segments"][0]["document_span"]["end"] -= 1
    elif source == "label_character":
        labels["characters"].pop()
    else:
        request["character_id"] = "char-cccccccccccccccccccc"
    with pytest.raises(ContractValidationError, match=message):
        build_render_ready_character_profiles(
            document_text=text,
            fact_groups=fact_groups,
            appearance_states=states,
            label_projection=labels,
            requests=[request],
        )


def test_run_writes_artifact_and_returns_summary(tmp_path: Path) -> None:
    text, fact_groups, states, labels = _fixture()
    fact_groups_file = tmp_path / "fact-groups.json"
    states_file = tmp_path / "states.json"
    labels_file = tmp_path / "labels.json"
    requests_file = tmp_path / "requests.json"
    output_file = tmp_path / "output" / "profiles.json"
    for path, value in (
        (fact_groups_file, fact_groups),
        (states_file, states),
        (labels_file, labels),
    ):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    requests_file.write_text(
        json.dumps(
            {
                "schema_version": RENDER_PROFILE_REQUESTS_VERSION,
                "requests": [
                    _request(
                        CHARACTER_A,
                        life="孩子",
                        form="unknown",
                        scene="unknown",
                        position=text.index("身形幼小"),
                    )
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    summary = run_render_ready_character_profiles(
        document_text=text,
        fact_groups_file=fact_groups_file,
        appearance_states_file=states_file,
        label_projection_file=labels_file,
        requests_file=requests_file,
        output_file=output_file,
    )
    written = json.loads(output_file.read_text(encoding="utf-8"))
    assert written["summary"] == summary
    assert summary["all_requests_compiled"] is True
