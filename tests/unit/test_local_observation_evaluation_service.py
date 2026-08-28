from pathlib import Path

from novel_character_generator.application.ports.local_observation import (
    LocalObservationDiscoveryResult,
)
from novel_character_generator.application.services.local_observation_evaluation_service import (
    LocalObservationEvaluationCase,
    _quote_match_rank,
    _unique_best_index,
    evaluate_local_observation_case,
    evaluate_local_observation_dataset,
    load_local_observation_evaluation_dataset,
)
from novel_character_generator.domain.entities.document import TextChunk
from novel_character_generator.domain.policies.text_processing import (
    build_chunks,
    decode_text,
    detect_chapters,
    normalize_text,
)

DATASET_PATH = Path("tests/evaluation/m1_local_observation_discovery_v1.json")
REAL_DATASET_PATH = Path("tests/evaluation/m1_local_observation_real_v1.json")


def _gold_output(case: LocalObservationEvaluationCase) -> LocalObservationDiscoveryResult:
    entity_ids = {
        item.key: f"e{index}" for index, item in enumerate(case.expected.entities, start=1)
    }
    fact_items = [*case.expected.required_facts, *case.expected.allowed_facts]
    fact_ids = {item.key: f"f{index}" for index, item in enumerate(fact_items, start=1)}
    return LocalObservationDiscoveryResult.model_validate(
        {
            "schema_version": "local-observation-discovery-v1.1",
            "chunk_id": case.input.chunk_id,
            "entities": [
                {
                    "local_entity_id": entity_ids[item.key],
                    "mention_quote": item.accepted_mentions[0],
                    "mention_kind": item.mention_kind,
                    "representative_name": item.accepted_mentions[0],
                }
                for item in case.expected.entities
            ],
            "facts": [
                {
                    "local_fact_id": fact_ids[item.key],
                    "entity_ref": entity_ids[item.owner_key],
                    "evidence_quote": item.evidence_quotes[0],
                    "raw_proposition": " ".join(
                        group[0] for group in item.proposition_concept_groups
                    )
                    or item.evidence_quotes[0],
                    "coarse_family": item.coarse_family,
                    "epistemic_status": item.epistemic_status,
                }
                for item in fact_items
            ],
            "temporal_signals": [
                {
                    "local_signal_id": f"t{index}",
                    "entity_ref": (
                        entity_ids[item.owner_key] if item.owner_key is not None else None
                    ),
                    "fact_ref": fact_ids[item.fact_key] if item.fact_key is not None else None,
                    "evidence_quote": item.evidence_quotes[0],
                    "signal_kind": item.signal_kind,
                    "raw_label": item.evidence_quotes[0],
                }
                for index, item in enumerate(case.expected.temporal_signals, start=1)
            ],
            "unresolved_items": [
                {
                    "local_item_id": f"u{index}",
                    "entity_ref": (
                        entity_ids[item.owner_key] if item.owner_key is not None else None
                    ),
                    "evidence_quote": item.evidence_quotes[0],
                    "raw_proposition": " ".join(
                        group[0] for group in item.proposition_concept_groups
                    )
                    or item.evidence_quotes[0],
                    "reason_code": item.reason_code,
                }
                for index, item in enumerate(case.expected.unresolved_items, start=1)
            ],
        }
    )


def test_m1_dataset_is_valid_reviewable_and_source_backed() -> None:
    dataset = load_local_observation_evaluation_dataset(DATASET_PATH)
    assert dataset.dataset_version == "m1-local-observation-v1.2"
    assert dataset.prompt_version == "local-observation-discovery-prompt-v1.6"
    assert dataset.review_status == "approved"
    assert len(dataset.cases) == 15
    assert len({case.category for case in dataset.cases}) >= 10

    for case in dataset.cases:
        for entity in case.expected.entities:
            assert any(item in case.input.chunk_text for item in entity.accepted_mentions)
        for fact in [*case.expected.required_facts, *case.expected.allowed_facts]:
            assert all(item in case.input.chunk_text for item in fact.evidence_quotes)
        for signal in case.expected.temporal_signals:
            assert all(item in case.input.chunk_text for item in signal.evidence_quotes)
        for item in case.expected.unresolved_items:
            assert all(value in case.input.chunk_text for value in item.evidence_quotes)


def test_real_m1_dataset_reconstructs_exact_production_chunks() -> None:
    dataset = load_local_observation_evaluation_dataset(REAL_DATASET_PATH)
    assert dataset.dataset_version == "m1-local-observation-real-v1.1"
    assert dataset.prompt_version == "local-observation-discovery-prompt-v1.6"
    assert dataset.review_status == "approved"
    assert len(dataset.cases) == 6
    assert len({case.source_chunk.path for case in dataset.cases if case.source_chunk}) == 4

    chunk_cache: dict[tuple[str, int], list[TextChunk]] = {}
    for case in dataset.cases:
        assert case.source_chunk is not None
        source = case.source_chunk
        cache_key = (source.path, source.chunk_tokens)
        if cache_key not in chunk_cache:
            raw_text, _encoding = decode_text(Path(source.path).read_bytes())
            normalized = normalize_text(raw_text)
            chunk_cache[cache_key] = build_chunks(
                normalized,
                detect_chapters(normalized.text),
                target_tokens=source.chunk_tokens,
            )
        chunk = chunk_cache[cache_key][source.chunk_ordinal]
        assert chunk.chapter_ordinal == source.chapter_ordinal
        assert chunk.content_hash == source.text_sha256
        assert chunk.content == case.input.chunk_text


def test_real_m1_gold_slices_score_perfect_after_user_approval() -> None:
    dataset = load_local_observation_evaluation_dataset(REAL_DATASET_PATH)
    outputs = {case.id: _gold_output(case) for case in dataset.cases}

    report = evaluate_local_observation_dataset(dataset, outputs)

    assert report.pass_count == 6
    assert report.review_count == 0
    assert report.fail_count == 0
    assert report.required_fact_recall == 1
    assert report.supported_fact_precision == 1
    assert report.temporal_signal_recall == 1
    assert report.temporal_signal_precision == 1
    assert report.unresolved_item_precision == 1
    assert report.quality_gate == "measured_no_release_gate"


def test_gold_outputs_score_perfect_on_approved_v1_1_regression() -> None:
    dataset = load_local_observation_evaluation_dataset(DATASET_PATH)
    outputs = {case.id: _gold_output(case) for case in dataset.cases}
    report = evaluate_local_observation_dataset(dataset, outputs)

    assert report.pass_count == 15
    assert report.review_count == 0
    assert report.fail_count == 0
    assert report.required_fact_recall == 1
    assert report.supported_fact_precision == 1
    assert report.quote_fidelity == 1
    assert report.epistemic_accuracy == 1
    assert report.temporal_signal_recall == 1
    assert report.temporal_signal_precision == 1
    assert report.unresolved_item_recall == 1
    assert report.unresolved_item_precision == 1
    assert report.required_fact_total == report.required_fact_matched
    assert report.actual_fact_total == report.supported_fact_total
    assert report.scored_actual_fact_total == report.supported_fact_total
    assert report.unscored_fact_total == 0
    assert report.temporal_signal_total == report.temporal_signal_matched
    assert report.actual_temporal_signal_total == report.temporal_signal_matched
    assert report.scored_actual_temporal_signal_total == report.temporal_signal_matched
    assert report.unscored_temporal_signal_total == 0
    assert report.unresolved_item_total == report.unresolved_item_matched
    assert report.actual_unresolved_item_total == report.unresolved_item_matched
    assert report.scored_actual_unresolved_item_total == report.unresolved_item_matched
    assert report.unscored_unresolved_item_total == 0
    assert report.quality_gate == "measured_no_release_gate"


def test_evaluator_separates_hard_epistemic_failure_from_wording_review() -> None:
    dataset = load_local_observation_evaluation_dataset(DATASET_PATH)
    case = next(item for item in dataset.cases if item.id == "m1-negated-scar-004")
    wrong_status = _gold_output(case).model_copy(deep=True)
    wrong_status.facts[0].epistemic_status = "asserted"
    failed = evaluate_local_observation_case(case, wrong_status)
    assert failed.status == "fail"
    assert failed.errors == ["wrong_epistemic_status:no_scar"]

    unusual_wording = _gold_output(case).model_copy(deep=True)
    unusual_wording.facts[0].raw_proposition = "面部特征与标注不一致"
    review = evaluate_local_observation_case(case, unusual_wording)
    assert review.status == "review"
    assert review.review_reasons == ["proposition_wording:no_scar"]


def test_evaluator_rejects_forbidden_held_object_fact() -> None:
    dataset = load_local_observation_evaluation_dataset(DATASET_PATH)
    case = next(item for item in dataset.cases if item.id == "m1-held-object-exclusion-010")
    output = _gold_output(case).model_copy(deep=True)
    output.facts.append(
        output.facts[0].model_copy(
            update={
                "local_fact_id": "f2",
                "evidence_quote": "一柄长剑",
                "raw_proposition": "顾川握着长剑",
                "coarse_family": "other_visual",
            }
        )
    )
    report = evaluate_local_observation_case(case, output)
    assert report.status == "fail"
    assert any(item.startswith("forbidden_fact:held_object") for item in report.errors)


def test_evaluator_leaves_unannotated_facts_unscored_for_real_chunk_slices() -> None:
    dataset = load_local_observation_evaluation_dataset(DATASET_PATH)
    original = next(item for item in dataset.cases if item.id == "m1-direct-two-facts-001")
    case = original.model_copy(deep=True)
    case.expected.allow_additional_facts = True
    output = _gold_output(case)
    output.facts.append(
        output.facts[0].model_copy(
            update={
                "local_fact_id": "f3",
                "evidence_quote": "沈砚",
                "raw_proposition": "沈砚是当前可见人物",
                "coarse_family": "physical_identity",
            }
        )
    )

    report = evaluate_local_observation_case(case, output)

    assert report.status == "pass"
    assert report.actual_fact_total == 3
    assert report.scored_actual_fact_total == 2
    assert report.unscored_fact_total == 1
    assert report.supported_fact_total == 2


def test_evaluator_accepts_a_unique_verbatim_extension_of_a_short_gold_quote() -> None:
    dataset = load_local_observation_evaluation_dataset(REAL_DATASET_PATH)
    case = next(item for item in dataset.cases if item.id == "m1-real-two-approximate-ages-002")
    output = _gold_output(case)
    jade_fact = next(item for item in output.facts if item.local_fact_id == "f4")
    jade_fact.evidence_quote = "娇嫩的耳垂上吊有着绿色的玉坠"

    report = evaluate_local_observation_case(case, output)

    assert report.status == "pass"
    assert report.required_fact_matched == report.required_fact_total


def test_safe_quote_extension_refuses_an_ambiguous_containment_match() -> None:
    actual = "娇嫩的耳垂上吊有着绿色的玉坠"
    gold = [["耳垂上吊有着绿色的玉坠"], ["绿色的玉坠"]]

    match = _unique_best_index(
        {0, 1},
        lambda index: _quote_match_rank(actual, gold[index]),
    )

    assert match is None


def test_evaluator_accepts_mixed_surface_kinds_for_one_chunk_local_owner() -> None:
    dataset = load_local_observation_evaluation_dataset(REAL_DATASET_PATH)
    case = next(
        item for item in dataset.cases if item.id == "m1-real-transformation-not-presentation-005"
    )
    output = _gold_output(case)
    output.entities.extend(
        [
            output.entities[0].model_copy(
                update={
                    "local_entity_id": "e2",
                    "mention_quote": "这个小女孩",
                    "mention_kind": "descriptor",
                    "representative_name": "这个小女孩",
                }
            ),
            output.entities[0].model_copy(
                update={
                    "local_entity_id": "e3",
                    "mention_quote": "庙中的怪物",
                    "mention_kind": "descriptor",
                    "representative_name": "庙中的怪物",
                }
            ),
        ]
    )
    for fact in output.facts[:3]:
        fact.entity_ref = "e2"
    output.facts[3].entity_ref = "e3"

    report = evaluate_local_observation_case(case, output)

    assert report.status == "pass"
    assert report.required_fact_matched == report.required_fact_total

    wrong_primary_kind = _gold_output(case)
    wrong_primary_kind.entities[0].mention_kind = "descriptor"
    failed = evaluate_local_observation_case(case, wrong_primary_kind)
    assert failed.status == "fail"
    assert "missing_entity:xian_qing_er" in failed.errors
