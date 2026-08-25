from novel_character_generator.domain.policies.grounding import repair_evidence_span
from novel_character_generator.domain.policies.visual_fields import (
    canonical_field_path,
    normalize_life_phase,
    normalize_observation_fields,
)


def test_combined_appearance_is_split_into_atomic_visual_fields() -> None:
    facts = normalize_observation_fields(
        "appearance",
        "小麦色皮肤，黑色短发，一身衣服虽然朴素但很干净",
        character_name="唐三",
    )

    assert {(item.field_path, item.value) for item in facts} == {
        ("skin.color", "小麦色"),
        ("hair.color", "黑色"),
        ("hair.length", "短发"),
        ("clothing.style", "朴素"),
        ("cleanliness", "干净"),
    }


def test_aliases_and_character_prefixes_are_canonicalized() -> None:
    assert canonical_field_path("appearance.build", character_name="唐三") == "body.build"
    assert canonical_field_path("唐三.appearance.build", character_name="唐三") == "body.build"
    assert canonical_field_path("唐三.ability", character_name="唐三") == "ability"


def test_life_phase_alias_is_normalized_with_default_label() -> None:
    assert normalize_life_phase("前世唐门", None) == ("past_life", "前世")
    assert normalize_life_phase(None, "转生幼年") == (
        "reincarnated_childhood",
        "转生幼年",
    )
    assert normalize_life_phase("reincarnated_childhood", "重生童年") == (
        "reincarnated_childhood",
        "转生幼年",
    )
    assert normalize_life_phase("past_life", "唐门前世") == ("past_life", "前世")


def test_age_stage_and_experienced_age_are_semantically_normalized() -> None:
    assert normalize_observation_fields("age_stage", "儿童")[0].value == "childhood"
    experienced_age = normalize_observation_fields(
        "age",
        "超过三十",
        evidence_quote="实际年龄早已超过了三十",
    )[0]
    assert experienced_age.field_path == "identity.experienced_age"
    mental_stage = normalize_observation_fields(
        "age_stage",
        "adult",
        evidence_quote="成年人心态的穿越者",
    )[0]
    assert mental_stage.field_path == "identity.mental_age_stage"


def test_common_soul_fact_paths_are_canonicalized() -> None:
    assert canonical_field_path("martial_soul") == "abilities.martial_spirit"
    assert canonical_field_path("soul_power.innate_full") == "abilities.innate_soul_power"


def test_unique_evidence_quote_repairs_incorrect_offsets() -> None:
    text = "唐三有小麦色皮肤和黑色短发。"
    quote = "小麦色皮肤和黑色短发"

    start, end, grounding = repair_evidence_span(text, quote, 0, len(quote))

    assert text[start:end] == quote
    assert grounding == "exact"


def test_repeated_quote_is_not_automatically_relocated() -> None:
    text = "黑发少年走来，另一个黑发少年离开。"

    start, end, grounding = repair_evidence_span(text, "黑发", 1, 3)

    assert (start, end) == (1, 3)
    assert grounding != "exact"
