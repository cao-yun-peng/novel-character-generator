import runpy
from pathlib import Path

import pytest

from novel_character_generator.application.ports.extraction import (
    GroundedVisualExtractionResult,
    ObservationDraft,
    VisualCandidateExtractionResult,
    VisualDeferredCandidate,
    VisualEntityCandidate,
    VisualFactCandidate,
    VisualTemporalSignal,
)
from novel_character_generator.application.services.extraction_evaluation_service import (
    ExpectedDeferredItem,
    ExpectedMention,
    ExpectedTemporalSignal,
    ExpectedVisualObservation,
    ExtractionSeedCase,
    ExtractionSeedDataset,
    ForbiddenVisualObservation,
    evaluate_extraction_case,
    evaluate_extraction_dataset,
    load_extraction_seed_dataset,
)
from novel_character_generator.application.services.visual_candidate_adapter import (
    adapt_visual_candidates,
    ground_visual_candidates,
)

SEED_PATH = Path(__file__).parents[1] / "evaluation" / "visual_extraction_seed_v0.json"
SEED_V1_PATH = Path(__file__).parents[1] / "evaluation" / "visual_extraction_seed_v1.json"


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


def test_v1_gold_dataset_is_strict_versioned_and_keeps_v0_reproducible() -> None:
    legacy = load_extraction_seed_dataset(SEED_PATH)
    dataset = load_extraction_seed_dataset(SEED_V1_PATH)

    assert legacy.version == "v0"
    assert len(legacy.cases) == 25
    assert dataset.version == "v1.1"
    assert dataset.rubric_version == "visual-observation-seed-v3.1"
    assert len(dataset.cases) == 31
    assert all(not case.expected_observations for case in dataset.cases)
    assert sum(len(case.effective_required_observations) for case in dataset.cases) == 40
    assert sum(len(case.allowed_observations) for case in dataset.cases) == 5
    assert sum(len(case.forbidden_observations) for case in dataset.cases) == 17
    assert sum(len(case.allowed_deferred_items) for case in dataset.cases) == 3


def test_v1_gold_corrects_clothing_type_color_and_style_boundaries() -> None:
    dataset = load_extraction_seed_dataset(SEED_V1_PATH)
    cases = {case.id: case for case in dataset.cases}

    direct = cases["direct-clothing-atomic"]
    assert {item.field_path for item in direct.required_observations} == {
        "clothing.type",
        "clothing.color",
        "cleanliness",
    }
    assert direct.forbidden_observations[0].field_path == "clothing.style"
    assert direct.forbidden_observations[0].values == ["灰色长袍"]

    disguise = cases["disguise-overlay"]
    assert "clothing.type" in {
        item.field_path for item in disguise.required_observations
    }
    assert disguise.forbidden_observations[0].field_path == "clothing.style"

    white_clothes = cases["repeated-phrase-two-owners"]
    assert {item.field_path for item in white_clothes.required_observations} == {
        "clothing.color"
    }
    assert {item.field_path for item in white_clothes.allowed_observations} == {
        "clothing.type"
    }


def test_allowed_observation_is_neither_required_nor_false_positive() -> None:
    case = ExtractionSeedCase(
        id="allowed-clothing-type",
        text="沈砚穿白衣。",
        required_observations=[
            ExpectedVisualObservation(
                character_name="沈砚",
                field_path="clothing.color",
                value="白色",
                evidence_quote="白衣",
            )
        ],
        allowed_observations=[
            ExpectedVisualObservation(
                character_name="沈砚",
                field_path="clothing.type",
                value="衣",
                accepted_values=["白衣"],
                evidence_quote="白衣",
            )
        ],
    )
    result = GroundedVisualExtractionResult(
        observations=[
            ObservationDraft(
                character_name="沈砚",
                field_path="clothing.color",
                value="白色",
                evidence_quote="白衣",
                start=3,
                end=5,
                confidence=1,
            ),
            ObservationDraft(
                character_name="沈砚",
                field_path="clothing.type",
                value="白衣",
                evidence_quote="白衣",
                start=3,
                end=5,
                confidence=1,
            ),
        ]
    )

    score = evaluate_extraction_case(case, result)

    assert score.status == "pass"
    assert score.true_positive == 1
    assert score.false_positive == 0
    assert score.false_negative == 0
    assert score.allowed_observation_count == 1


def test_partial_real_audit_counts_but_does_not_penalize_unlisted_observation() -> None:
    case = ExtractionSeedCase(
        id="partial-audit",
        text="沈砚有黑发，穿白衣。",
        required_observations=[
            ExpectedVisualObservation(
                character_name="沈砚",
                field_path="hair.color",
                value="黑色",
                evidence_quote="黑发",
            )
        ],
        allow_unlisted_observations=True,
    )
    result = GroundedVisualExtractionResult(
        observations=[
            ObservationDraft(
                character_name="沈砚",
                field_path="hair.color",
                value="黑色",
                evidence_quote="黑发",
                start=3,
                end=5,
                confidence=1,
            ),
            ObservationDraft(
                character_name="沈砚",
                field_path="clothing.color",
                value="白色",
                evidence_quote="白衣",
                start=7,
                end=9,
                confidence=1,
            ),
        ]
    )

    score = evaluate_extraction_case(case, result)

    assert score.status == "pass"
    assert score.false_positive == 0
    assert score.unlisted_observation_count == 1


def test_unrelated_same_field_fact_does_not_mask_a_missing_required_observation() -> None:
    case = ExtractionSeedCase(
        id="same-field-different-garment",
        text="萧薰儿露出紫袖，身上穿着紫裙。",
        required_observations=[
            ExpectedVisualObservation(
                character_name="萧薰儿",
                field_path="clothing.type",
                value="衣袖",
                accepted_values=["紫袖", "袖"],
                evidence_quote="紫袖",
            )
        ],
        allow_unlisted_observations=True,
    )
    result = GroundedVisualExtractionResult(
        observations=[
            ObservationDraft(
                character_name="萧薰儿",
                field_path="clothing.type",
                value="紫裙",
                evidence_quote="穿着紫裙",
                start=13,
                end=17,
                confidence=1,
            )
        ]
    )

    score = evaluate_extraction_case(case, result)

    assert score.status == "fail"
    assert score.true_positive == 0
    assert score.false_negative == 1
    assert score.false_positive == 0
    assert score.unlisted_observation_count == 1


def test_forbidden_observation_has_an_auditable_failure_reason() -> None:
    case = ExtractionSeedCase(
        id="forbidden-style",
        text="顾遥穿着灰色长袍。",
        forbidden_observations=[
            ForbiddenVisualObservation(
                character_name="顾遥",
                field_path="clothing.style",
                values=["灰色长袍"],
                reason="garment_bundle_is_not_clothing_style",
            )
        ],
    )
    result = GroundedVisualExtractionResult(
        observations=[
            ObservationDraft(
                character_name="顾遥",
                field_path="clothing.style",
                value="灰色长袍",
                evidence_quote="灰色长袍",
                start=4,
                end=8,
                confidence=1,
            )
        ]
    )

    score = evaluate_extraction_case(case, result)

    assert score.status == "fail"
    assert score.forbidden_observation_count == 1
    assert score.false_positive == 1
    assert score.observations[0].reason_codes == [
        "forbidden_observation",
        "garment_bundle_is_not_clothing_style",
    ]


def test_descriptor_kind_is_scored_independently_from_visual_fact() -> None:
    case = ExtractionSeedCase(
        id="descriptor-kind",
        text="少女戴着绿色玉坠。",
        required_observations=[
            ExpectedVisualObservation(
                character_name="少女",
                field_path="accessories.earrings",
                value="绿色玉坠",
                evidence_quote="绿色玉坠",
            )
        ],
        expected_mentions=[
            ExpectedMention(
                surface="少女",
                mention_kind="descriptor",
                max_count=1,
            )
        ],
    )
    candidates = VisualCandidateExtractionResult(
        entities=[
            VisualEntityCandidate(
                local_id="girl",
                representative_name="少女",
                mention_quote="少女",
                mention_kind="explicit_name",
                confidence=1,
            )
        ],
        visual_candidates=[
            VisualFactCandidate(
                entity_ref="girl",
                field_path="accessories.earrings",
                value="绿色玉坠",
                evidence_quote="绿色玉坠",
                confidence=1,
            )
        ],
    )
    grounded = adapt_visual_candidates(case.text, candidates)
    packet = ground_visual_candidates(
        case.text,
        candidates,
        mention_id_prefix=case.id,
    )

    score = evaluate_extraction_case(
        case,
        grounded,
        candidates=candidates,
        packet=packet,
    )

    assert score.true_positive == 1
    assert score.mention_failure_count == 1
    assert score.status == "fail"
    assert any(
        reason.startswith("wrong_mention_kind:少女:explicit_name")
        for reason in score.contract_reason_codes
    )


def test_owner_alias_and_raw_candidate_mention_are_scored_without_grounding_loss() -> None:
    case = ExtractionSeedCase(
        id="owner-and-surface-alias",
        text="青年站得身形挺拔。",
        required_observations=[
            ExpectedVisualObservation(
                character_name="男子",
                accepted_character_names=["青年"],
                field_path="body.build",
                value="挺拔",
                evidence_quote="身形挺拔",
            )
        ],
        expected_mentions=[
            ExpectedMention(
                surface="男子",
                accepted_surfaces=["青年"],
                mention_kind="descriptor",
            )
        ],
    )
    candidates = VisualCandidateExtractionResult(
        entities=[
            VisualEntityCandidate(
                local_id="youth",
                representative_name="青年",
                mention_quote="青年",
                mention_kind="descriptor",
                confidence=1,
            )
        ]
    )
    actual = GroundedVisualExtractionResult(
        observations=[
            ObservationDraft(
                character_name="青年",
                field_path="body.build",
                value="挺拔",
                evidence_quote="身形挺拔",
                start=4,
                end=8,
                confidence=1,
            )
        ]
    )

    score = evaluate_extraction_case(
        case,
        actual,
        candidates=candidates,
        packet=ground_visual_candidates(
            case.text,
            VisualCandidateExtractionResult(),
            mention_id_prefix=case.id,
        ),
    )

    assert score.status == "pass"
    assert score.true_positive == 1
    assert score.mention_failure_count == 0


def test_allowed_deferred_is_optional_but_unlisted_deferred_still_fails() -> None:
    case = ExtractionSeedCase(
        id="safe-deferred",
        text="程岳面容清俊，轮廓并未作具体说明。",
        allowed_deferred_items=[
            ExpectedDeferredItem(
                reason_code="unsupported_visual_field",
                evidence_quote="轮廓并未作具体说明",
            )
        ],
    )
    allowed = VisualCandidateExtractionResult(
        deferred_items=[
            VisualDeferredCandidate(
                reason_code="unsupported_visual_field",
                evidence_quote="轮廓并未作具体说明",
            )
        ]
    )
    unexpected = VisualCandidateExtractionResult(
        deferred_items=[
            VisualDeferredCandidate(
                reason_code="uncertain_visual_fact",
                evidence_quote="面容清俊",
            )
        ]
    )

    assert evaluate_extraction_case(
        case,
        GroundedVisualExtractionResult(),
        candidates=allowed,
    ).status == "pass"
    score = evaluate_extraction_case(
        case,
        GroundedVisualExtractionResult(),
        candidates=unexpected,
    )
    assert score.status == "fail"
    assert score.deferred_failure_count == 1


def test_inferred_age_must_be_deferred_without_an_asserted_fact() -> None:
    case = ExtractionSeedCase(
        id="inferred-age",
        text="那名男子看起来像四十岁左右。",
        forbidden_observations=[
            ForbiddenVisualObservation(
                character_name="那名男子",
                field_path="age",
                reason="inferred_age_must_not_be_asserted",
            )
        ],
        expected_deferred_items=[
            ExpectedDeferredItem(
                reason_code="inferred_visual_fact",
                evidence_quote="看起来像四十岁左右",
                max_count=1,
            )
        ],
    )
    candidates = VisualCandidateExtractionResult(
        deferred_items=[
            VisualDeferredCandidate(
                reason_code="inferred_visual_fact",
                evidence_quote="看起来像四十岁左右",
            )
        ]
    )

    score = evaluate_extraction_case(
        case,
        GroundedVisualExtractionResult(),
        candidates=candidates,
    )

    assert score.status == "pass"
    assert score.deferred_failure_count == 0

    asserted = _coverage_result(
        "四十岁左右",
        evidence_quote="看起来像四十岁左右",
        field_path="age",
    )
    asserted.observations[0].character_name = "那名男子"
    score = evaluate_extraction_case(case, asserted, candidates=candidates)
    assert score.status == "fail"
    assert score.forbidden_observation_count == 1


def test_required_temporal_signal_is_scored_with_owner_and_evidence() -> None:
    case = ExtractionSeedCase(
        id="age-signal",
        text="苏棠只有七岁。",
        required_observations=[
            ExpectedVisualObservation(
                character_name="苏棠",
                field_path="age",
                value="七岁",
                evidence_quote="只有七岁",
            )
        ],
        expected_temporal_signals=[
            ExpectedTemporalSignal(
                kind="age",
                label="七岁",
                evidence_quote="只有七岁",
                character_name="苏棠",
            )
        ],
    )
    candidates = VisualCandidateExtractionResult(
        entities=[
            VisualEntityCandidate(
                local_id="sut",
                representative_name="苏棠",
                mention_quote="苏棠",
                mention_kind="explicit_name",
                confidence=1,
            )
        ],
        visual_candidates=[
            VisualFactCandidate(
                entity_ref="sut",
                field_path="age",
                value="七岁",
                evidence_quote="只有七岁",
                confidence=1,
                temporal_signals=[
                    VisualTemporalSignal(
                        kind="age",
                        label="七岁",
                        evidence_quote="只有七岁",
                    )
                ],
            )
        ],
    )
    packet = ground_visual_candidates(
        case.text,
        candidates,
        mention_id_prefix=case.id,
    )

    passing = evaluate_extraction_case(
        case,
        adapt_visual_candidates(case.text, candidates),
        candidates=candidates,
        packet=packet,
    )
    missing = evaluate_extraction_case(
        case,
        GroundedVisualExtractionResult(),
        candidates=VisualCandidateExtractionResult(),
        packet=ground_visual_candidates(
            case.text,
            VisualCandidateExtractionResult(),
            mention_id_prefix="missing-age-signal",
        ),
    )

    assert passing.status == "pass"
    assert passing.false_positive == 0
    assert passing.temporal_failure_count == 0
    assert missing.status == "fail"
    assert missing.temporal_failure_count == 1
    assert missing.contract_reason_codes == ["missing_temporal_signal:age:七岁"]


def test_temporal_signal_accepts_narrow_evidence_span_and_dedupes_for_scoring() -> None:
    case = ExtractionSeedCase(
        id="age-signal-dedupe",
        text="苏棠以十四岁年龄进入学院。",
        expected_temporal_signals=[
            ExpectedTemporalSignal(
                kind="age",
                label="十四岁",
                evidence_quote="十四岁年龄",
                character_name="苏棠",
            )
        ],
        allow_unlisted_observations=True,
    )
    signal = VisualTemporalSignal(
        kind="age",
        label="十四岁",
        evidence_quote="以十四岁年龄",
    )
    candidates = VisualCandidateExtractionResult(
        entities=[
            VisualEntityCandidate(
                local_id="sut",
                representative_name="苏棠",
                mention_quote="苏棠",
                mention_kind="explicit_name",
                confidence=1,
            )
        ],
        visual_candidates=[
            VisualFactCandidate(
                entity_ref="sut",
                field_path="age",
                value="十四岁",
                evidence_quote="十四岁年龄",
                confidence=1,
                temporal_signals=[signal],
            )
        ],
        temporal_signals=[
            {
                "entity_ref": "sut",
                "kind": "age",
                "label": "十四岁",
                "evidence_quote": "以十四岁年龄",
                "confidence": 1,
            }
        ],
    )
    packet = ground_visual_candidates(
        case.text,
        candidates,
        mention_id_prefix=case.id,
    )

    score = evaluate_extraction_case(
        case,
        adapt_visual_candidates(case.text, candidates),
        candidates=candidates,
        packet=packet,
    )

    assert score.status == "pass"
    assert score.temporal_failure_count == 0
    assert score.duplicate_temporal_signal_count == 1


def test_asserted_and_deferred_same_evidence_is_an_exclusive_branch_failure() -> None:
    case = ExtractionSeedCase(
        id="exclusive-branch-collision",
        text="那名男子看起来像四十岁左右。",
        allow_unlisted_observations=True,
        allow_unlisted_deferred=True,
    )
    candidates = VisualCandidateExtractionResult(
        entities=[
            VisualEntityCandidate(
                local_id="man",
                representative_name="那名男子",
                mention_quote="那名男子",
                mention_kind="descriptor",
                confidence=1,
            )
        ],
        visual_candidates=[
            VisualFactCandidate(
                entity_ref="man",
                field_path="age",
                value="四十岁左右",
                evidence_quote="看起来像四十岁左右",
                confidence=1,
            )
        ],
        deferred_items=[
            VisualDeferredCandidate(
                reason_code="inferred_visual_fact",
                evidence_quote="看起来像四十岁左右",
            )
        ],
    )

    score = evaluate_extraction_case(
        case,
        adapt_visual_candidates(case.text, candidates),
        candidates=candidates,
    )

    assert score.status == "fail"
    assert score.asserted_deferred_collision_count == 1
    assert score.contract_reason_codes == [
        "asserted_deferred_collision:看起来像四十岁左右"
    ]


def test_v31_dataset_rejects_semantically_invalid_gold_field() -> None:
    with pytest.raises(ValueError, match="seed_expected_field_semantic_issue"):
        ExtractionSeedDataset(
            name="invalid-gold",
            version="v1.1",
            rubric_version="visual-observation-seed-v3.1",
            cases=[
                ExtractionSeedCase(
                    id="invalid-insignia",
                    text="少女衣襟绘有三颗金星。",
                    required_observations=[
                        ExpectedVisualObservation(
                            character_name="少女",
                            field_path="clothing.insignia",
                            value="三颗金星",
                            evidence_quote="绘有三颗金星",
                        )
                    ],
                )
            ],
        )


def test_real_chunk_manifest_resolves_six_source_backed_audited_slices() -> None:
    script = Path(__file__).parents[1] / "测试" / "ab_evaluate_visual_prompts.py"
    module = runpy.run_path(str(script))
    loader = module["_load_real_samples"]
    manifest = Path(__file__).parents[1] / "evaluation" / "r1_prompt_ab_real_v1.json"

    samples, cases = loader(manifest)

    assert len(samples) == 6
    assert len(cases) == 6
    assert {sample["annotation_status"] for sample in samples} == {
        "audited-slice-v1.1"
    }
    assert all(case.allow_unlisted_observations for case in cases.values())
    assert sum(len(case.effective_required_observations) for case in cases.values()) == 14
    assert sum(len(case.forbidden_observations) for case in cases.values()) == 11


def test_ab_contract_metrics_expose_duplicates_and_asserted_deferred_collision() -> None:
    script = Path(__file__).parents[1] / "测试" / "ab_evaluate_visual_prompts.py"
    metrics_for = runpy.run_path(str(script))["_contract_metrics"]
    fact = VisualFactCandidate(
        entity_ref="girl",
        field_path="accessories.earrings",
        value="绿色玉坠",
        evidence_quote="绿色玉坠",
        confidence=1,
    )
    candidates = VisualCandidateExtractionResult(
        entities=[
            VisualEntityCandidate(
                local_id="girl",
                representative_name="少女",
                mention_quote="少女",
                mention_kind="descriptor",
                confidence=1,
            )
        ],
        visual_candidates=[fact, fact.model_copy(deep=True)],
        deferred_items=[
            VisualDeferredCandidate(
                reason_code="uncertain_visual_fact",
                evidence_quote="绿色玉坠",
            )
        ],
    )
    packet = ground_visual_candidates(
        "少女戴着绿色玉坠。",
        candidates,
        mention_id_prefix="duplicates",
    )

    metrics = metrics_for(candidates, packet)

    assert metrics["duplicate_visual_candidate_count"] == 1
    assert metrics["duplicate_grounded_fact_count"] == 1
    assert metrics["asserted_deferred_collision_count"] == 1
    assert metrics["asserted_deferred_collision_quotes"] == ["绿色玉坠"]
