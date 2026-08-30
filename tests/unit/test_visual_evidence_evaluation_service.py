from pathlib import Path

import pytest

from novel_character_generator.application.ports.model_provider import ModelCallMetadata
from novel_character_generator.application.ports.visual_evidence import (
    DetailedVisualEvidenceResult,
    GroundedEvidenceCandidate,
    VisualEvidenceDiscoveryInput,
    VisualEvidenceDiscoveryResult,
    VisualEvidenceExecutionRequest,
    VisualEvidenceMention,
)
from novel_character_generator.application.services.visual_evidence_evaluation_service import (
    VisualEvidenceEvaluationCase,
    evaluate_visual_evidence_dataset,
    load_visual_evidence_evaluation_dataset,
)
from novel_character_generator.application.services.visual_evidence_service import (
    VisualEvidenceContractError,
    VisualEvidenceShadowService,
    validate_visual_evidence_output,
)
from scripts.run_m1_visual_evidence_evaluation import execute_dataset

SHORT_DATASET = Path("tests/evaluation/m1_visual_evidence_discovery_v2.json")
REAL_DATASET = Path("tests/evaluation/m1_visual_evidence_real_v2.json")


def _result(
    case: VisualEvidenceEvaluationCase,
    *,
    mentions: tuple[VisualEvidenceMention, ...] = (),
    candidates: tuple[GroundedEvidenceCandidate, ...] = (),
) -> VisualEvidenceDiscoveryResult:
    return VisualEvidenceDiscoveryResult(
        schema_version="visual-evidence-discovery-v2",
        chunk_id=case.input.chunk_id,
        mentions=mentions,
        evidence_candidates=candidates,
    )


def _gold_result(case: VisualEvidenceEvaluationCase) -> VisualEvidenceDiscoveryResult:
    owner_mentions: dict[str, VisualEvidenceMention] = {}
    candidates: list[GroundedEvidenceCandidate] = []
    expected_owners = {item.key: item for item in case.expected.owners}
    for index, item in enumerate(case.expected.required_candidates, start=1):
        local_owner_id = None
        if item.owner_policy == "required":
            assert item.owner_key is not None
            if item.owner_key not in owner_mentions:
                mention_id = f"m{len(owner_mentions) + 1}"
                owner_mentions[item.owner_key] = VisualEvidenceMention(
                    mention_id=mention_id,
                    mention_quote=expected_owners[item.owner_key].accepted_mentions[0],
                )
            local_owner_id = owner_mentions[item.owner_key].mention_id
        candidates.append(
            GroundedEvidenceCandidate(
                candidate_id=f"c{index}",
                local_owner_id=local_owner_id,
                evidence_quote=item.evidence_quotes[0],
            )
        )
    return _result(
        case,
        mentions=tuple(owner_mentions.values()),
        candidates=tuple(candidates),
    )


def test_v23_draft_short_dataset_contains_corrected_gold_and_owner_policies() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    assert dataset.schema_version == "visual-evidence-evaluation-dataset-v2.2"
    assert dataset.dataset_version == "m1-visual-evidence-short-v2.3-draft"
    assert dataset.review_status == "draft_user_review_required"
    assert len(dataset.cases) == 16

    cases = {case.id: case for case in dataset.cases}
    descriptor = cases["m1-v2-descriptor-003"]
    descriptor_owner = descriptor.expected.owners[0]
    descriptor_candidate = descriptor.expected.required_candidates[0]
    assert "一个红衣少女" in descriptor_owner.accepted_mentions
    assert "一个红衣少女" in descriptor_candidate.evidence_quotes
    inferred = cases["m1-v2-inferred-age-006"].expected.required_candidates[0]
    explicit = cases["m1-v2-explicit-age-007"].expected.required_candidates[0]
    must_be_null = cases[
        "m1-v2-owner-must-be-null-016"
    ].expected.required_candidates[0]
    assert inferred.evidence_quotes == ["从他满头白发看来，他约莫已有六十岁"]
    assert explicit.evidence_quotes == ["十二岁的唐宁个子瘦小"]
    assert {inferred.owner_policy, explicit.owner_policy, must_be_null.owner_policy} == {
        "allowed",
        "required",
        "must_be_null",
    }


def test_v23_draft_scorer_tracks_missing_outputs_without_release_gate() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    report = evaluate_visual_evidence_dataset(dataset, {})
    assert report.rubric_version == "visual-evidence-evaluation-rubric-v2.5"
    assert report.quality_gate == "blocked_pending_user_review"
    assert report.review_count == 16
    assert report.evidence_coverage_recall == 0


def test_v23_draft_short_gold_outputs_score_perfectly() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    outputs = {case.id: _gold_result(case) for case in dataset.cases}
    report = evaluate_visual_evidence_dataset(dataset, outputs)
    assert report.quality_gate == "blocked_pending_user_review"
    assert report.pass_count == 16
    assert report.review_count == 0
    assert report.fail_count == 0
    assert report.evidence_coverage_recall == 1
    assert report.quote_fidelity == 1


def test_required_owner_must_be_bound_to_an_accepted_mention() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    case = next(item for item in dataset.cases if item.id == "m1-v2-multi-owner-002")
    correct = _result(
        case,
        mentions=(
            VisualEvidenceMention(mention_id="m1", mention_quote="苏璃"),
            VisualEvidenceMention(mention_id="m2", mention_quote="顾川"),
        ),
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1", local_owner_id="m1", evidence_quote="苏璃头戴银簪"
            ),
            GroundedEvidenceCandidate(
                candidate_id="c2", local_owner_id="m2", evidence_quote="顾川披着黑色斗篷"
            ),
        ),
    )
    missing_binding = _result(
        case,
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1", local_owner_id=None, evidence_quote="苏璃头戴银簪"
            ),
            GroundedEvidenceCandidate(
                candidate_id="c2", local_owner_id=None, evidence_quote="顾川披着黑色斗篷"
            ),
        ),
    )
    assert evaluate_visual_evidence_dataset(dataset, {case.id: correct}).cases[1].status == "pass"
    failed = evaluate_visual_evidence_dataset(dataset, {case.id: missing_binding}).cases[1]
    assert failed.status == "fail"
    assert failed.owner_required_matched == 0


def test_allowed_owner_accepts_null_or_correct_binding() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    case = next(item for item in dataset.cases if item.id == "m1-v2-inferred-age-006")
    quote = "从他满头白发看来，他约莫已有六十岁"
    null_owner = _result(
        case,
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1", local_owner_id=None, evidence_quote=quote
            ),
        ),
    )
    bound_owner = _result(
        case,
        mentions=(VisualEvidenceMention(mention_id="m1", mention_quote="他"),),
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1", local_owner_id="m1", evidence_quote=quote
            ),
        ),
    )
    reports = [
        evaluate_visual_evidence_dataset(dataset, {case.id: output})
        for output in (null_owner, bound_owner)
    ]
    assert all(report.cases[5].status == "pass" for report in reports)


def test_must_be_null_owner_rejects_binding() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    case = next(
        item for item in dataset.cases if item.id == "m1-v2-owner-must-be-null-016"
    )
    quote = "一只戴着银环的手"
    null_owner = _result(
        case,
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1", local_owner_id=None, evidence_quote=quote
            ),
        ),
    )
    bound_owner = _result(
        case,
        mentions=(VisualEvidenceMention(mention_id="m1", mention_quote="一只"),),
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1", local_owner_id="m1", evidence_quote=quote
            ),
        ),
    )
    passed = evaluate_visual_evidence_dataset(dataset, {case.id: null_owner}).cases[-1]
    failed = evaluate_visual_evidence_dataset(dataset, {case.id: bound_owner}).cases[-1]
    assert passed.status == "pass"
    assert passed.owner_must_be_null_matched == 1
    assert failed.status == "fail"


def test_evaluator_hard_fails_non_verbatim_quote() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    case = dataset.cases[0]
    output = _result(
        case,
        mentions=(VisualEvidenceMention(mention_id="m1", mention_quote="沈砚"),),
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1",
                local_owner_id="m1",
                evidence_quote="沈砚有黑色短发，穿灰色长袍",
            ),
        ),
    )
    scored = evaluate_visual_evidence_dataset(dataset, {case.id: output}).cases[0]
    assert scored.status == "fail"
    assert "visual_evidence_quote_not_in_chunk" in scored.errors


def test_evaluator_rejects_non_unique_evidence_quote() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    case = dataset.cases[0].model_copy(deep=True)
    case.input.chunk_text = "沈砚留着黑色短发。沈砚留着黑色短发。"
    case.expected.required_candidates[0].evidence_quotes = ["沈砚留着黑色短发"]
    output = _result(
        case,
        mentions=(VisualEvidenceMention(mention_id="m1", mention_quote="沈砚"),),
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1",
                local_owner_id="m1",
                evidence_quote="沈砚留着黑色短发",
            ),
        ),
    )
    scored = evaluate_visual_evidence_dataset(
        dataset.model_copy(update={"cases": [case]}),
        {case.id: output},
    ).cases[0]
    assert scored.status == "fail"
    assert "evidence_quote_not_uniquely_locatable:0" in scored.errors
    assert scored.quote_valid == 1


def test_real_dataset_reconstructs_ten_production_chunks() -> None:
    dataset = load_visual_evidence_evaluation_dataset(
        REAL_DATASET,
        project_root=Path.cwd(),
    )
    assert dataset.schema_version == "visual-evidence-evaluation-dataset-v2.4"
    assert dataset.dataset_version == "m1-visual-evidence-real-v2.5-draft"
    assert dataset.review_status == "draft_user_review_required"
    assert len(dataset.cases) == 10
    paths = {case.source_chunk.path for case in dataset.cases if case.source_chunk}
    assert len(paths) == 4
    assert all(case.source_chunk is not None for case in dataset.cases)


def test_v25_real_dataset_covers_observed_valid_owner_aliases_and_spans() -> None:
    dataset = load_visual_evidence_evaluation_dataset(
        REAL_DATASET,
        project_root=Path.cwd(),
    )
    cases = {case.id: case for case in dataset.cases}
    expected_aliases = {
        "m1-v2-real-xiao-yan-xiao-mei-001": ("xiao_mei", "萧媚"),
        "m1-v2-real-xun-er-002": ("xun_er", "萧薰儿"),
        "m1-v2-real-tang-san-child-003": (
            "tang_san",
            "那是个只有五、六岁的孩子",
        ),
    }
    for case_id, (owner_key, mention) in expected_aliases.items():
        owners = {item.key: item for item in cases[case_id].expected.owners}
        assert mention in owners[owner_key].accepted_mentions

    new_aliases = (
        ("m1-v2-real-tang-san-child-003", "tang_san", "他"),
        ("m1-v2-real-tang-hao-dense-004", "tang_hao", "那是一名中年男子"),
        ("m1-v2-real-relative-age-accessory-008", "xian_qinger", "那女孩儿"),
        ("m1-v2-real-transformation-009", "xian_qinger", "小女孩仙清儿"),
    )
    for case_id, owner_key, mention in new_aliases:
        owners = {item.key: item for item in cases[case_id].expected.owners}
        assert mention in owners[owner_key].accepted_mentions

    inferred = cases["m1-v2-real-inferred-age-007"].expected.required_candidates
    spans = {item.key: item.evidence_quotes for item in inferred}
    assert "唐昊看起来却要比他们苍老的多，反倒像是唐三的爷爷一般" in spans[
        "older_than_peers_inference"
    ]
    assert "暗黄的脸色" in spans["sallow_face"]

    age_and_braids = cases[
        "m1-v2-real-relative-age-accessory-008"
    ].expected.required_candidates[1]
    assert (
        "小女孩儿，年纪与他仿佛，也是十一二岁，梳着三根小辫，"
        "两根较细的辫子垂在胸前，粗的辫子垂在身后"
    ) in age_and_braids.evidence_quotes


def test_v24_dataset_rejects_owner_alias_shared_across_local_people() -> None:
    dataset = load_visual_evidence_evaluation_dataset(REAL_DATASET)
    raw_case = dataset.cases[0].model_dump(mode="json")
    raw_case["expected"]["owners"][1]["accepted_mentions"].append("少年")
    with pytest.raises(ValueError, match="ambiguous_expected_visual_owner_mention"):
        VisualEvidenceEvaluationCase.model_validate(raw_case)


def test_v24_rubric_allows_one_candidate_covering_multiple_gold_items() -> None:
    dataset = load_visual_evidence_evaluation_dataset(REAL_DATASET)
    case = dataset.cases[3]
    first, second = case.expected.required_candidates
    start = case.input.chunk_text.index(first.evidence_quotes[0])
    end = case.input.chunk_text.index(second.evidence_quotes[0]) + len(
        second.evidence_quotes[0]
    )
    combined = case.input.chunk_text[start:end]
    output = _result(
        case,
        mentions=(VisualEvidenceMention(mention_id="m1", mention_quote="中年男子"),),
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1",
                local_owner_id="m1",
                evidence_quote=combined,
            ),
        ),
    )
    scored = evaluate_visual_evidence_dataset(dataset, {case.id: output}).cases[3]
    assert scored.status == "pass"
    assert scored.required_candidate_matched == 2
    assert scored.actual_candidate_total == 1
    assert scored.scored_actual_candidate_total == 1
    assert scored.unscored_candidate_total == 0
    assert scored.correct_owner_binding_total == 1


def test_real_dataset_distinguishes_qing_robed_and_moon_white_elders() -> None:
    dataset = load_visual_evidence_evaluation_dataset(
        REAL_DATASET,
        project_root=Path.cwd(),
    )
    case = next(
        item
        for item in dataset.cases
        if item.id == "m1-v2-real-presentation-and-elder-005"
    )
    owners = {item.key: item for item in case.expected.owners}
    qing = owners["qing_robed_steward"]
    moon_white = owners["moon_white_elder"]
    assert "老者" not in qing.accepted_mentions
    assert "老者" in moon_white.accepted_mentions
    assert "老人" in moon_white.accepted_mentions
    assert "墨管家" in qing.accepted_mentions
    assert "一位身穿月白衣袍的老者" in moon_white.accepted_mentions

    candidates = {
        item.key: item for item in case.expected.required_candidates
    }
    qing_candidate = candidates["qing_robed_steward_clothing"]
    moon_white_candidate = candidates["moon_white_elder_visual_profile"]
    assert qing_candidate.owner_key == "qing_robed_steward"
    assert qing_candidate.evidence_quotes == ["一名青衫老者"]
    assert moon_white_candidate.owner_key == "moon_white_elder"
    assert (
        "身穿月白衣袍的老者，老者满脸笑容，神采奕奕，一双有些细小的双眼，却是精光偶闪"
        in moon_white_candidate.evidence_quotes
    )


def test_real_dataset_gold_outputs_score_without_failures_or_reviews() -> None:
    dataset = load_visual_evidence_evaluation_dataset(
        REAL_DATASET,
        project_root=Path.cwd(),
    )
    outputs = {case.id: _gold_result(case) for case in dataset.cases}
    report = evaluate_visual_evidence_dataset(dataset, outputs)
    assert report.pass_count == 10
    assert report.review_count == 0
    assert report.fail_count == 0
    assert report.evidence_coverage_recall == 1
    assert report.quote_fidelity == 1


def test_scorer_rejects_held_object_only_candidate() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    case = dataset.cases[9]
    output = _result(
        case,
        mentions=(VisualEvidenceMention(mention_id="m1", mention_quote="顾川"),),
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1", local_owner_id="m1", evidence_quote="握着一柄长剑"
            ),
        ),
    )
    scored = evaluate_visual_evidence_dataset(dataset, {case.id: output}).cases[9]
    assert scored.status == "fail"
    assert any("held_object_only" in item for item in scored.errors)


def test_scorer_allows_held_object_inside_a_matched_appearance_span() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    case = dataset.cases[9]
    output = _result(
        case,
        mentions=(VisualEvidenceMention(mention_id="m1", mention_quote="顾川"),),
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1",
                local_owner_id="m1",
                evidence_quote="顾川握着一柄长剑，腰间却系着一条红色腰带",
            ),
        ),
    )
    scored = evaluate_visual_evidence_dataset(dataset, {case.id: output}).cases[9]
    assert scored.status == "pass"
    assert scored.required_candidate_matched == 1


def test_v24_real_apparel_allows_adjacent_weapons_and_mounts() -> None:
    dataset = load_visual_evidence_evaluation_dataset(REAL_DATASET)
    case = dataset.cases[9]
    assert case.expected.forbidden_candidates == []
    output = _result(
        case,
        mentions=(
            VisualEvidenceMention(mention_id="m1", mention_quote="史进"),
            VisualEvidenceMention(mention_id="m2", mention_quote="陈达"),
        ),
        candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1",
                local_owner_id="m1",
                evidence_quote=(
                    "史进头戴一字巾，身披朱红甲，上穿青锦袄，下着抹绿靴，腰系皮搭膊，"
                    "前后铁掩心，一张弓，一壶箭，手里拿一把三尖两刃四窍八环刀"
                ),
            ),
            GroundedEvidenceCandidate(
                candidate_id="c2",
                local_owner_id="m2",
                evidence_quote=(
                    "陈达头戴干红凹面巾，身披裹金生铁甲，上穿一领红衲袄，脚穿一对吊墩靴，"
                    "腰系七尺攒线搭膊，坐骑一匹高头白马，手中横着丈八点钢矛"
                ),
            ),
        ),
    )
    scored = evaluate_visual_evidence_dataset(dataset, {case.id: output}).cases[9]
    assert scored.status == "pass"
    assert scored.required_candidate_matched == 2


def test_service_validates_chunk_id_deterministically() -> None:
    output = VisualEvidenceDiscoveryResult(
        schema_version="visual-evidence-discovery-v2",
        chunk_id="different-chunk",
        mentions=(),
        evidence_candidates=(),
    )
    with pytest.raises(VisualEvidenceContractError) as raised:
        validate_visual_evidence_output(
            "当前 Chunk 文本",
            output,
            expected_chunk_id="current-chunk",
        )
    assert raised.value.code == "visual_evidence_chunk_id_mismatch"


def test_service_rejects_evidence_that_n2_cannot_locate_uniquely() -> None:
    output = VisualEvidenceDiscoveryResult(
        schema_version="visual-evidence-discovery-v2",
        chunk_id="repeated-chunk",
        mentions=(),
        evidence_candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1",
                local_owner_id=None,
                evidence_quote="黑色短发",
            ),
        ),
    )
    with pytest.raises(VisualEvidenceContractError) as raised:
        validate_visual_evidence_output(
            "他留着黑色短发，另一个人也留着黑色短发。",
            output,
            expected_chunk_id="repeated-chunk",
        )
    assert raised.value.code == "visual_evidence_quote_not_unique_in_chunk"


def test_service_canonicalizes_unique_whitespace_only_difference() -> None:
    output = VisualEvidenceDiscoveryResult(
        schema_version="visual-evidence-discovery-v2",
        chunk_id="whitespace-chunk",
        mentions=(),
        evidence_candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1",
                local_owner_id=None,
                evidence_quote="第一句。第二句。",
            ),
        ),
    )
    validated = validate_visual_evidence_output(
        "段首。\n　　第一句。\r\n  第二句。段尾。",
        output,
        expected_chunk_id="whitespace-chunk",
    )
    assert validated.evidence_candidates[0].evidence_quote == (
        "第一句。\r\n  第二句。"
    )


def test_service_rejects_punctuation_change_after_whitespace_normalization() -> None:
    output = VisualEvidenceDiscoveryResult(
        schema_version="visual-evidence-discovery-v2",
        chunk_id="punctuation-chunk",
        mentions=(),
        evidence_candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1",
                local_owner_id=None,
                evidence_quote="第一句，第二句。",
            ),
        ),
    )
    with pytest.raises(VisualEvidenceContractError) as raised:
        validate_visual_evidence_output(
            "第一句。\n　　第二句。",
            output,
            expected_chunk_id="punctuation-chunk",
        )
    assert raised.value.code == "visual_evidence_quote_not_in_chunk"


def test_service_rejects_multiple_matches_after_whitespace_normalization() -> None:
    output = VisualEvidenceDiscoveryResult(
        schema_version="visual-evidence-discovery-v2",
        chunk_id="ambiguous-whitespace-chunk",
        mentions=(),
        evidence_candidates=(
            GroundedEvidenceCandidate(
                candidate_id="c1",
                local_owner_id=None,
                evidence_quote="黑色短发",
            ),
        ),
    )
    with pytest.raises(VisualEvidenceContractError) as raised:
        validate_visual_evidence_output(
            "他留着黑 色短发，另一个人也留着黑色短发。",
            output,
            expected_chunk_id="ambiguous-whitespace-chunk",
        )
    assert raised.value.code == "visual_evidence_quote_not_unique_in_chunk"


class _NonVerbatimProvider:
    version = "fake-m1-v2"
    model_config_version = "fake-m1-config-v1"
    prompt_version = "visual-evidence-discovery-prompt-v2.8"
    prompt_hash = "e" * 64

    async def discover_detailed(
        self, request: VisualEvidenceDiscoveryInput
    ) -> DetailedVisualEvidenceResult:
        return DetailedVisualEvidenceResult(
            output=VisualEvidenceDiscoveryResult(
                schema_version="visual-evidence-discovery-v2",
                chunk_id=request.chunk_id,
                mentions=(),
                evidence_candidates=(
                    GroundedEvidenceCandidate(
                        candidate_id="c1",
                        local_owner_id=None,
                        evidence_quote="模型改写而非原文",
                    ),
                ),
            ),
            metadata=ModelCallMetadata(
                wire_api="chat_completions",
                status="succeeded",
                latency_ms=1,
            ),
        )


class _WhitespaceOnlyProvider:
    version = "fake-m1-v2"
    model_config_version = "fake-m1-config-v1"
    prompt_version = "visual-evidence-discovery-prompt-v2.8"
    prompt_hash = "f" * 64

    async def discover_detailed(
        self, request: VisualEvidenceDiscoveryInput
    ) -> DetailedVisualEvidenceResult:
        return DetailedVisualEvidenceResult(
            output=VisualEvidenceDiscoveryResult(
                schema_version="visual-evidence-discovery-v2",
                chunk_id=request.chunk_id,
                mentions=(),
                evidence_candidates=(
                    GroundedEvidenceCandidate(
                        candidate_id="c1",
                        local_owner_id=None,
                        evidence_quote="第一句。第二句。",
                    ),
                ),
            ),
            metadata=ModelCallMetadata(
                wire_api="chat_completions",
                status="succeeded",
                latency_ms=1,
            ),
        )


@pytest.mark.asyncio
async def test_shadow_service_canonicalizes_whitespace_before_artifact_hash() -> None:
    request = VisualEvidenceExecutionRequest(
        run_id="whitespace-run",
        source_document_version_id="source-v1",
        data_policy_version="policy-v1",
        evaluation_attempt_id="attempt-1",
        payload=VisualEvidenceDiscoveryInput(
            schema_version="visual-evidence-discovery-input-v2",
            chunk_id="whitespace-chunk",
            chunk_text="第一句。\n　　第二句。",
        ),
    )
    artifact = await VisualEvidenceShadowService(  # type: ignore[arg-type]
        _WhitespaceOnlyProvider()
    ).run(request)
    assert artifact.status == "completed_with_warnings"
    assert artifact.reason_codes == ("source_whitespace_canonicalized",)
    assert artifact.output.evidence_candidates[0].evidence_quote == (
        "第一句。\n　　第二句。"
    )


@pytest.mark.asyncio
async def test_real_runner_passes_outputs_through_deterministic_validation() -> None:
    dataset = load_visual_evidence_evaluation_dataset(SHORT_DATASET)
    outputs, case_runs = await execute_dataset(
        dataset.model_copy(update={"cases": [dataset.cases[0]]}),
        _NonVerbatimProvider(),  # type: ignore[arg-type]
        run_id="test-run",
        source_document_version_id="test-source",
        evaluation_attempt_id="test-attempt",
    )
    case_id = dataset.cases[0].id
    assert outputs[case_id]["evidence_candidates"][0]["evidence_quote"] == (
        "模型改写而非原文"
    )
    assert case_runs[0]["status"] == "deterministic_validation_failed"
    assert case_runs[0]["reason_codes"] == ["visual_evidence_quote_not_in_chunk"]
    scored = evaluate_visual_evidence_dataset(
        dataset.model_copy(update={"cases": [dataset.cases[0]]}),
        {case_id: VisualEvidenceDiscoveryResult.model_validate(outputs[case_id])},
    )
    assert scored.fail_count == 1
