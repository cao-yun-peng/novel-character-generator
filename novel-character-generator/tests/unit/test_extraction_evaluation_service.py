from pathlib import Path

import pytest

from novel_character_generator.application.ports.extraction import (
    GroundedVisualExtractionResult,
    ObservationDraft,
)
from novel_character_generator.application.services.extraction_evaluation_service import (
    ExpectedVisualObservation,
    ExtractionSeedCase,
    ExtractionSeedDataset,
    evaluate_extraction_case,
    evaluate_extraction_dataset,
    load_extraction_seed_dataset,
)

SEED_PATH = Path(__file__).parents[1] / "evaluation" / "visual_extraction_seed_v0.json"


def test_seed_dataset_is_versioned_and_covers_positive_negative_and_critical_cases() -> None:
    dataset = load_extraction_seed_dataset(SEED_PATH)

    assert dataset.version == "v0"
    assert dataset.rubric_version == "visual-observation-seed-v2"
    assert len(dataset.cases) == 25
    assert any(not case.expected_observations for case in dataset.cases)
    assert any(case.severity == "critical" for case in dataset.cases)
    assert {
        "life-phase",
        "negative",
        "ambiguous-pronoun",
        "approximate-age",
        "beard",
        "eyes",
        "negative-inference",
        "face-description",
        "tattoo",
        "coverage",
        "shared-evidence",
    } <= {tag for case in dataset.cases for tag in case.slice_tags}


def test_live_difference_cases_are_generic_and_use_canonical_visual_fields() -> None:
    dataset = load_extraction_seed_dataset(SEED_PATH)
    cases = {
        case.id: case
        for case in dataset.cases
        if case.id
        in {
            "approximate-age-perception",
            "canonical-beard-field",
            "canonical-eye-state-field",
            "no-inferred-cleanliness-from-grooming",
        }
    }

    assert len(cases) == 4
    assert cases["approximate-age-perception"].expected_observations == []
    assert {item.field_path for item in cases["canonical-beard-field"].expected_observations} == {
        "distinctive_marks.beard"
    }
    assert {
        item.field_path for item in cases["canonical-eye-state-field"].expected_observations
    } == {"face.eyes"}
    grooming_paths = {
        item.field_path
        for item in cases["no-inferred-cleanliness-from-grooming"].expected_observations
    }
    assert grooming_paths == {"hair.style", "distinctive_marks.beard"}
    assert all(
        "cleanliness" not in item.field_path
        for item in cases["no-inferred-cleanliness-from-grooming"].expected_observations
    )


def test_cross_genre_difference_cases_are_atomic_and_canonical() -> None:
    dataset = load_extraction_seed_dataset(SEED_PATH)
    cases = {case.id: case for case in dataset.cases}

    assert {
        item.field_path for item in cases["eye-color-versus-gaze-state"].expected_observations
    } == {"face.eye_color", "face.eyes"}
    assert cases["reported-attractiveness-not-complexion"].expected_observations == []
    assert {
        item.field_path for item in cases["clothing-coverage-not-body-build"].expected_observations
    } == {"clothing.coverage"}
    assert {item.field_path for item in cases["tattoo-not-scar"].expected_observations} == {
        "distinctive_marks.tattoo"
    }
    assert len(cases["compound-outfit-atomic"].expected_observations) == 6
    assert {
        item.field_path for item in cases["white-hair-and-beard-atomic"].expected_observations
    } == {"hair.color", "distinctive_marks.beard"}
    coverage = cases["clothing-coverage-not-body-build"].expected_observations[0]
    beard = next(
        item
        for item in cases["white-hair-and-beard-atomic"].expected_observations
        if item.field_path == "distinctive_marks.beard"
    )
    assert coverage.accepted_values == ["赤着上身"]
    assert beard.accepted_values == ["长须雪白"]


def test_case_score_separates_structure_from_compatible_evidence_span() -> None:
    dataset = load_extraction_seed_dataset(SEED_PATH)
    case = next(item for item in dataset.cases if item.id == "direct-hair")
    result = GroundedVisualExtractionResult(
        observations=[
            ObservationDraft(
                character_name="沈砚",
                field_path="hair.color",
                value="黑色",
                evidence_quote="黑色短发",
                start=4,
                end=8,
                confidence=1,
            ),
            ObservationDraft(
                character_name="沈砚",
                field_path="hair.length",
                value="短",
                evidence_quote="短发",
                start=6,
                end=8,
                confidence=1,
            ),
        ]
    )

    score = evaluate_extraction_case(case, result)

    assert score.precision == 1
    assert score.recall == 1
    assert score.exact_evidence_rate == 0.5
    assert score.compatible_evidence_rate == 1
    assert score.status == "pass"
    assert score.passed is True


def _coverage_case() -> ExtractionSeedCase:
    return ExtractionSeedCase(
        id="coverage-boundary",
        text="顾川赤着上身站在雨中。",
        expected_observations=[
            ExpectedVisualObservation(
                character_name="顾川",
                field_path="clothing.coverage",
                value="上身未着衣",
                accepted_values=["赤着上身"],
                rejected_values=["身材健壮"],
                evidence_quote="赤着上身",
            )
        ],
    )


def _coverage_result(
    value: str,
    *,
    evidence_quote: str = "赤着上身",
    field_path: str = "clothing.coverage",
) -> GroundedVisualExtractionResult:
    return GroundedVisualExtractionResult(
        observations=[
            ObservationDraft(
                character_name="顾川",
                field_path=field_path,
                value=value,
                evidence_quote=evidence_quote,
                start=2,
                end=6,
                confidence=1,
            )
        ]
    )


def test_value_boundary_passes_known_variant_reviews_unknown_and_fails_rejected() -> None:
    case = _coverage_case()

    accepted = evaluate_extraction_case(case, _coverage_result("赤着上身"))
    unknown = evaluate_extraction_case(case, _coverage_result("上半身裸露"))
    rejected = evaluate_extraction_case(case, _coverage_result("身材健壮"))

    assert accepted.status == "pass"
    assert accepted.observations[0].value_match == "accepted"
    assert unknown.status == "needs_review"
    assert unknown.observations[0].reason_codes == ["unrecognized_value_variant"]
    assert rejected.status == "fail"
    assert rejected.observations[0].reason_codes == ["known_rejected_value"]


def test_evidence_boundary_passes_containment_reviews_other_span_and_fails_ungrounded() -> None:
    case = _coverage_case()

    contained = evaluate_extraction_case(
        case,
        _coverage_result("赤着上身", evidence_quote="顾川赤着上身"),
    )
    other_span = evaluate_extraction_case(
        case,
        _coverage_result("赤着上身", evidence_quote="站在雨中"),
    )
    ungrounded = evaluate_extraction_case(
        case,
        _coverage_result("赤着上身", evidence_quote="并不存在的证据"),
    )

    assert contained.status == "pass"
    assert contained.observations[0].evidence_match == "contained"
    assert other_span.status == "needs_review"
    assert "unrecognized_evidence_span" in other_span.observations[0].reason_codes
    assert ungrounded.status == "fail"
    assert "ungrounded_evidence" in ungrounded.observations[0].reason_codes


def test_wrong_field_fails_even_when_value_and_evidence_look_plausible() -> None:
    score = evaluate_extraction_case(
        _coverage_case(),
        _coverage_result("赤着上身", field_path="body.build"),
    )

    assert score.status == "fail"
    assert score.false_positive == 1
    assert score.false_negative == 1
    assert {reason for item in score.observations for reason in item.reason_codes} == {
        "missing_observation",
        "unexpected_observation",
    }


def test_life_phase_mismatch_is_a_structural_failure() -> None:
    result = _coverage_result("赤着上身")
    result.observations[0].life_phase_key = "childhood"

    score = evaluate_extraction_case(_coverage_case(), result)

    assert score.status == "fail"
    assert score.false_positive == 1
    assert score.false_negative == 1


def test_dataset_score_counts_review_cases_separately() -> None:
    case = _coverage_case()
    dataset = ExtractionSeedDataset(
        name="boundary-dataset",
        version="v0",
        rubric_version="visual-observation-seed-v2",
        cases=[case],
    )

    score = evaluate_extraction_dataset(
        dataset,
        {case.id: _coverage_result("上半身裸露")},
    )

    assert score.passed_case_count == 0
    assert score.needs_review_case_count == 1
    assert score.failed_case_count == 0
    assert score.precision == 1
    assert score.recall == 1
    assert score.accepted_value_rate == 0


def test_negative_case_rejects_visual_hallucination() -> None:
    dataset = load_extraction_seed_dataset(SEED_PATH)
    case = next(item for item in dataset.cases if item.id == "negative-occupation")
    hallucination = GroundedVisualExtractionResult(
        observations=[
            ObservationDraft(
                character_name="周宁",
                field_path="clothing.style",
                value="白大褂",
                evidence_quote="医生",
                start=10,
                end=12,
                epistemic_status="inferred",
                confidence=0.4,
            )
        ]
    )

    assert evaluate_extraction_case(case, GroundedVisualExtractionResult()).passed is True
    score = evaluate_extraction_case(case, hallucination)
    assert score.false_positive == 1
    assert score.status == "fail"
    assert score.passed is False


def test_dataset_score_requires_output_for_every_case() -> None:
    dataset = load_extraction_seed_dataset(SEED_PATH)

    with pytest.raises(ValueError, match="missing_seed_case_outputs"):
        evaluate_extraction_dataset(dataset, {})
