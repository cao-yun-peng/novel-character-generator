from pathlib import Path

from novel_character_generator.application.ports.local_observation import (
    LocalObservationDiscoveryResult,
)
from novel_character_generator.application.services.local_observation_evaluation_service import (
    LocalObservationEvaluationCase,
    evaluate_local_observation_case,
    evaluate_local_observation_dataset,
    load_local_observation_evaluation_dataset,
)

DATASET_PATH = Path("tests/evaluation/m1_local_observation_discovery_v1.json")


def _gold_output(case: LocalObservationEvaluationCase) -> LocalObservationDiscoveryResult:
    entity_ids = {
        item.key: f"e{index}"
        for index, item in enumerate(case.expected.entities, start=1)
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
    assert dataset.dataset_version == "m1-local-observation-v1.1-draft2"
    assert dataset.review_status == "draft_user_review_required"
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


def test_gold_outputs_score_perfect_but_gate_waits_for_v1_1_review() -> None:
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
    assert report.temporal_signal_total == report.temporal_signal_matched
    assert report.actual_temporal_signal_total == report.temporal_signal_matched
    assert report.unresolved_item_total == report.unresolved_item_matched
    assert report.actual_unresolved_item_total == report.unresolved_item_matched
    assert report.quality_gate == "blocked_pending_user_review"


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
    case = next(
        item for item in dataset.cases if item.id == "m1-held-object-exclusion-010"
    )
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
