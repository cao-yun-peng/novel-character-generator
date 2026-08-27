import pytest

from novel_character_generator.domain.policies.visual_query_plan import (
    QUERY_PLAN_VERSION,
    build_visual_query_plan,
    observation_applies_to_phase,
    resolve_requested_life_phase,
    score_visual_field_group,
    visual_field_group,
)


def test_visual_query_plan_is_deterministic_and_contains_entity_free_queries() -> None:
    first = build_visual_query_plan(
        canonical_name="萧炎",
        aliases=["炎儿", "萧炎", "炎儿"],
        field_groups=["hair", "clothing", "hair"],
        life_phase_key="adolescence",
        max_provider_calls=1,
        context_budget_tokens=4_000,
    )
    second = build_visual_query_plan(
        canonical_name="萧炎",
        aliases=["炎儿"],
        field_groups=["hair", "clothing"],
        life_phase_key="adolescence",
        max_provider_calls=1,
        context_budget_tokens=4_000,
    )

    assert first.version == QUERY_PLAN_VERSION
    assert first.aliases == ("炎儿",)
    assert first.field_groups == ("hair", "clothing")
    assert first.fingerprint == second.fingerprint
    assert any(query["kind"] == "semantic_field:hair" for query in first.queries)
    assert any(
        "萧炎" not in query["text"]
        for query in first.queries
        if query["kind"].startswith("semantic_field:")
    )


def test_visual_query_plan_rejects_unknown_field_group() -> None:
    with pytest.raises(ValueError, match="unsupported_visual_field_groups:weapon"):
        build_visual_query_plan(
            canonical_name="萧炎",
            aliases=[],
            field_groups=["weapon"],
            life_phase_key=None,
            max_provider_calls=1,
            context_budget_tokens=4_000,
        )


@pytest.mark.parametrize(
    ("field_path", "group"),
    [
        ("hair.color", "hair"),
        ("skin.color", "body"),
        ("face.injury", "marks_injuries"),
        ("accessory.waist", "accessories"),
        ("cleanliness", "disguise_cleanliness"),
        ("occupation", None),
    ],
)
def test_visual_field_group_mapping(field_path: str, group: str | None) -> None:
    assert visual_field_group(field_path) == group


def test_face_requires_more_than_one_eye_color_field() -> None:
    score, required, missing = score_visual_field_group("face", {"face.eye_color"})

    assert score == pytest.approx(1 / 3)
    assert score < required
    assert missing == ("shape", "features")


def test_complete_hair_requires_color_and_form() -> None:
    score, required, missing = score_visual_field_group(
        "hair", {"hair.color", "hair.length"}
    )

    assert score == required == 1.0
    assert missing == ()


def test_generic_age_stage_resolves_only_one_matching_narrative_phase() -> None:
    resolved = resolve_requested_life_phase(
        "childhood",
        phase_age_stages={"village_years": {"childhood"}, "academy_years": {"adolescence"}},
        normalized_age_stage="childhood",
    )

    assert resolved == "village_years"
    assert observation_applies_to_phase(None, resolved) is False
    assert observation_applies_to_phase("village_years", resolved) is True


def test_generic_age_stage_rejects_ambiguous_narrative_phases() -> None:
    with pytest.raises(ValueError, match="ambiguous_life_phase"):
        resolve_requested_life_phase(
            "childhood",
            phase_age_stages={"before_exile": {"childhood"}, "after_exile": {"childhood"}},
            normalized_age_stage="childhood",
        )
