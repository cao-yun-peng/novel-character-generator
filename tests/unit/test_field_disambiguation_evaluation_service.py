from pathlib import Path

from novel_character_generator.application.ports.field_disambiguation import (
    FieldDisambiguationModelOutput,
    FieldDisambiguationResult,
)
from novel_character_generator.application.services.field_disambiguation_evaluation_service import (
    build_field_disambiguation_evaluation_packet,
    evaluate_field_disambiguation_case,
    evaluate_field_disambiguation_dataset,
    load_field_disambiguation_evaluation_dataset,
)
from novel_character_generator.infrastructure.llm.field_disambiguation import (
    materialize_field_disambiguation_result,
)

DATASET_PATH = Path("tests/evaluation/m2_field_disambiguation_v1.json")


def _gold_output(
    case_index: int,
    *,
    split_all_units: bool = False,
) -> FieldDisambiguationResult:
    dataset = load_field_disambiguation_evaluation_dataset(DATASET_PATH)
    case = dataset.cases[case_index]
    unit_indices: dict[str, int] = {}
    decisions = []
    for expected in case.expected:
        mappings = []
        for mapping_index, mapping in enumerate(expected.mappings):
            if split_all_units:
                semantic_unit_index = mapping_index
            else:
                semantic_unit_index = unit_indices.setdefault(
                    mapping.semantic_unit_key,
                    len(unit_indices),
                )
            mappings.append(
                {
                    "semantic_unit_index": semantic_unit_index,
                    "referent_kind": mapping.referent_kind,
                    "referent_quote": mapping.accepted_referent_quotes[0],
                    "field_path": mapping.field_path,
                    "normalized_value": mapping.accepted_values[0],
                }
            )
        decisions.append(
            {
                "fact_index": expected.fact_index,
                "decision": expected.decision,
                "mappings": mappings,
                "reason_code": expected.reason_code,
            }
        )
    packet = build_field_disambiguation_evaluation_packet(case)
    return materialize_field_disambiguation_result(
        packet,
        FieldDisambiguationModelOutput.model_validate({"decisions": decisions}),
    )


def test_m2_draft_dataset_loads_with_frozen_versions_and_categories() -> None:
    dataset = load_field_disambiguation_evaluation_dataset(DATASET_PATH)
    assert dataset.dataset_version == "m2-field-disambiguation-v1-draft1"
    assert dataset.review_status == "draft_user_review_required"
    assert dataset.node_contract_version == "field-disambiguation-contract-v1"
    assert dataset.field_registry_version == "visual-field-catalog-v1"
    assert len(dataset.cases) == 9
    assert {case.category for case in dataset.cases} >= {
        "atomic_mapping",
        "semantic_grouping",
        "defer",
        "reject",
        "value_policy",
    }
    for case in dataset.cases:
        packet = build_field_disambiguation_evaluation_packet(case)
        assert len(packet.grounded_facts) == len(case.input.facts)


def test_m2_evaluator_accepts_contract_exact_expected_outputs_but_keeps_gate_blocked() -> None:
    dataset = load_field_disambiguation_evaluation_dataset(DATASET_PATH)
    outputs = {case.id: _gold_output(index) for index, case in enumerate(dataset.cases)}
    report = evaluate_field_disambiguation_dataset(dataset, outputs)
    assert report.pass_count == 9
    assert report.fail_count == 0
    assert report.decision_accuracy == 1
    assert report.mapping_accuracy == 1
    assert report.semantic_grouping_accuracy == 1
    assert report.quality_gate == "blocked_pending_user_review"


def test_m2_evaluator_rejects_split_dimensions_of_the_same_referent() -> None:
    dataset = load_field_disambiguation_evaluation_dataset(DATASET_PATH)
    case = dataset.cases[2]
    report = evaluate_field_disambiguation_case(case, _gold_output(2, split_all_units=True))
    assert report.status == "fail"
    assert any(
        "wrong_semantic_grouping" in error
        for error in report.errors
    )
