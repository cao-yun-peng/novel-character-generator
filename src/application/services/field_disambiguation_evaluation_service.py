from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from novel_character_generator.application.ports.field_disambiguation import (
    FIELD_DISAMBIGUATION_CONTRACT_VERSION,
    FIELD_DISAMBIGUATION_PROMPT_VERSION,
    FieldDecision,
    FieldDecisionReasonCode,
    FieldDisambiguationResult,
    ReferentKind,
)
from novel_character_generator.application.ports.local_grounding import (
    GroundedEvidenceSpan,
    GroundedLocalFact,
    GroundedLocalPacket,
    GroundedMentionNode,
    LocalContextWindow,
)
from novel_character_generator.application.ports.local_observation import (
    CoarseVisualFamily,
    EpistemicStatus,
)
from novel_character_generator.application.services.field_disambiguation_service import (
    FieldDisambiguationContractError,
    validate_field_disambiguation_output,
)
from novel_character_generator.domain.policies.visual_field_catalog import (
    VISUAL_FIELD_CATALOG_VERSION,
)

M2_EVALUATION_DATASET_SCHEMA_VERSION: Literal[
    "field-disambiguation-evaluation-dataset-v1"
] = "field-disambiguation-evaluation-dataset-v1"
M2_EVALUATION_RUBRIC_VERSION: Literal["field-disambiguation-evaluation-rubric-v1"] = (
    "field-disambiguation-evaluation-rubric-v1"
)


class FieldDisambiguationEvaluationFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_quote: str = Field(min_length=1)
    raw_proposition: str = Field(min_length=1)
    coarse_family: CoarseVisualFamily
    epistemic_status: EpistemicStatus


class FieldDisambiguationEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    chunk_text: str = Field(min_length=1)
    owner_mention: str = Field(min_length=1)
    facts: list[FieldDisambiguationEvaluationFact] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_quotes(self) -> FieldDisambiguationEvaluationInput:
        if self.owner_mention not in self.chunk_text:
            raise ValueError("m2_evaluation_owner_not_in_chunk")
        for fact in self.facts:
            if self.chunk_text.count(fact.evidence_quote) != 1:
                raise ValueError("m2_evaluation_fact_quote_must_be_unique")
        return self


class ExpectedFieldMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str = Field(min_length=1)
    accepted_values: list[str] = Field(min_length=1)
    referent_kind: ReferentKind
    accepted_referent_quotes: list[str | None] = Field(min_length=1)
    semantic_unit_key: str = Field(min_length=1)


class ExpectedFieldDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_index: int = Field(ge=0)
    decision: FieldDecision
    reason_code: FieldDecisionReasonCode
    mappings: list[ExpectedFieldMapping]

    @model_validator(mode="after")
    def validate_expected_shape(self) -> ExpectedFieldDecision:
        if self.decision == "map" and not self.mappings:
            raise ValueError("m2_expected_map_requires_mapping")
        if self.decision != "map" and self.mappings:
            raise ValueError("m2_expected_non_map_has_mapping")
        return self


class FieldDisambiguationEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input: FieldDisambiguationEvaluationInput
    expected: list[ExpectedFieldDecision] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_expected_coverage(self) -> FieldDisambiguationEvaluationCase:
        indices = [item.fact_index for item in self.expected]
        if len(indices) != len(set(indices)) or set(indices) != set(range(len(self.input.facts))):
            raise ValueError("m2_evaluation_expected_coverage_invalid")
        return self


class FieldDisambiguationEvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["field-disambiguation-evaluation-dataset-v1"]
    dataset_version: str = Field(min_length=1)
    node_contract_version: Literal["field-disambiguation-contract-v1"]
    field_registry_version: Literal["visual-field-catalog-v1"]
    prompt_version: Literal["field-disambiguation-prompt-v1"]
    review_status: Literal["draft_user_review_required", "approved"]
    review_notes: list[str]
    cases: list[FieldDisambiguationEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> FieldDisambiguationEvaluationDataset:
        case_ids = [item.id for item in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate_m2_evaluation_case_id")
        return self


class FieldDisambiguationCaseEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    status: Literal["pass", "fail"]
    errors: list[str]
    decision_total: int = Field(ge=0)
    decision_matched: int = Field(ge=0)
    mapping_total: int = Field(ge=0)
    mapping_matched: int = Field(ge=0)
    grouping_pair_total: int = Field(ge=0)
    grouping_pair_matched: int = Field(ge=0)


class FieldDisambiguationEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_version: Literal["field-disambiguation-evaluation-rubric-v1"]
    dataset_version: str
    dataset_review_status: Literal["draft_user_review_required", "approved"]
    quality_gate: Literal["blocked_pending_user_review", "measured_no_release_gate"]
    pass_count: int = Field(ge=0)
    fail_count: int = Field(ge=0)
    decision_accuracy: float = Field(ge=0, le=1)
    mapping_accuracy: float = Field(ge=0, le=1)
    semantic_grouping_accuracy: float = Field(ge=0, le=1)
    cases: list[FieldDisambiguationCaseEvaluation]


def load_field_disambiguation_evaluation_dataset(
    path: Path,
) -> FieldDisambiguationEvaluationDataset:
    return FieldDisambiguationEvaluationDataset.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_field_disambiguation_evaluation_packet(
    case: FieldDisambiguationEvaluationCase,
) -> GroundedLocalPacket:
    source = case.input
    mention_start = source.chunk_text.index(source.owner_mention)
    mention_end = mention_start + len(source.owner_mention)
    facts: list[GroundedLocalFact] = []
    for index, item in enumerate(source.facts, start=1):
        start = source.chunk_text.index(item.evidence_quote)
        end = start + len(item.evidence_quote)
        facts.append(
            GroundedLocalFact(
                fact_id=f"gf_{_sha256(f'{case.id}:f{index}')[:32]}",
                local_fact_id=f"f{index}",
                local_entity_id="e1",
                evidence_quote=item.evidence_quote,
                evidence_span=GroundedEvidenceSpan(
                    start=start,
                    end=end,
                    source_quote=item.evidence_quote,
                    quote_hash=_sha256(item.evidence_quote),
                ),
                grounding_status="exact",
                raw_proposition=item.raw_proposition,
                coarse_family=item.coarse_family,
                epistemic_status=item.epistemic_status,
                local_context=LocalContextWindow(
                    policy_version="local-context-sentence-window-v1",
                    start=0,
                    end=len(source.chunk_text),
                    text=source.chunk_text,
                    focus_start=start,
                    focus_end=end,
                    context_hash=_sha256(source.chunk_text),
                ),
            )
        )
    return GroundedLocalPacket(
        schema_version="grounded-local-packet-v1",
        run_id=f"m2-eval-{case.id}",
        source_document_version_id="m2-evaluation-source-v1",
        chunk_id=source.chunk_id,
        grounding_policy_version="local-grounding-policy-v1",
        context_policy_version="local-context-sentence-window-v1",
        mention_nodes=(
            GroundedMentionNode(
                local_entity_id="e1",
                mention_quote=source.owner_mention,
                mention_kind="explicit_name",
                representative_name=source.owner_mention,
                grounding_status="exact",
                occurrence_count=source.chunk_text.count(source.owner_mention),
                evidence_span=GroundedEvidenceSpan(
                    start=mention_start,
                    end=mention_end,
                    source_quote=source.owner_mention,
                    quote_hash=_sha256(source.owner_mention),
                ),
            ),
        ),
        grounded_facts=tuple(facts),
        grounded_signals=(),
        rejected_items=(),
        deferred_items=(),
    )


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def evaluate_field_disambiguation_case(
    case: FieldDisambiguationEvaluationCase,
    output: FieldDisambiguationResult,
) -> FieldDisambiguationCaseEvaluation:
    packet = build_field_disambiguation_evaluation_packet(case)
    errors: list[str] = []
    try:
        validate_field_disambiguation_output(packet, output)
    except FieldDisambiguationContractError as error:
        errors.append(f"contract:{error.code}")

    decisions_by_fact_id = {item.fact_id: item for item in output.decisions}
    decision_matched = 0
    mapping_total = 0
    mapping_matched = 0
    grouping_pair_total = 0
    grouping_pair_matched = 0
    for expected in case.expected:
        fact = packet.grounded_facts[expected.fact_index]
        actual = decisions_by_fact_id.get(fact.fact_id)
        if actual is None:
            errors.append(f"missing_decision:{expected.fact_index}")
            mapping_total += len(expected.mappings)
            continue
        if actual.decision != expected.decision or actual.reason_code != expected.reason_code:
            errors.append(f"wrong_decision:{expected.fact_index}")
        else:
            decision_matched += 1

        mapping_total += len(expected.mappings)
        unmatched_actual = set(range(len(actual.mappings)))
        matched_units: list[tuple[str, str]] = []
        for expected_mapping in expected.mappings:
            matches = [
                index
                for index in unmatched_actual
                if actual.mappings[index].field_path == expected_mapping.field_path
                and actual.mappings[index].referent_kind == expected_mapping.referent_kind
                and _normalized(actual.mappings[index].normalized_value)
                in {_normalized(value) for value in expected_mapping.accepted_values}
                and actual.mappings[index].referent_quote
                in expected_mapping.accepted_referent_quotes
            ]
            if len(matches) != 1:
                errors.append(
                    f"missing_or_ambiguous_mapping:{expected.fact_index}:"
                    f"{expected_mapping.field_path}"
                )
                continue
            actual_index = matches[0]
            unmatched_actual.remove(actual_index)
            mapping_matched += 1
            matched_units.append(
                (expected_mapping.semantic_unit_key, actual.mappings[actual_index].semantic_unit_id)
            )
        if unmatched_actual:
            errors.append(f"unexpected_mappings:{expected.fact_index}:{len(unmatched_actual)}")

        for left in range(len(matched_units)):
            for right in range(left + 1, len(matched_units)):
                grouping_pair_total += 1
                expected_same = matched_units[left][0] == matched_units[right][0]
                actual_same = matched_units[left][1] == matched_units[right][1]
                if expected_same == actual_same:
                    grouping_pair_matched += 1
                else:
                    errors.append(f"wrong_semantic_grouping:{expected.fact_index}")

    return FieldDisambiguationCaseEvaluation(
        case_id=case.id,
        status="fail" if errors else "pass",
        errors=errors,
        decision_total=len(case.expected),
        decision_matched=decision_matched,
        mapping_total=mapping_total,
        mapping_matched=mapping_matched,
        grouping_pair_total=grouping_pair_total,
        grouping_pair_matched=grouping_pair_matched,
    )


def evaluate_field_disambiguation_dataset(
    dataset: FieldDisambiguationEvaluationDataset,
    outputs_by_case_id: dict[str, FieldDisambiguationResult],
) -> FieldDisambiguationEvaluationReport:
    expected_ids = {item.id for item in dataset.cases}
    if set(outputs_by_case_id) != expected_ids:
        raise ValueError("m2_evaluation_output_case_ids_mismatch")
    reports = [
        evaluate_field_disambiguation_case(case, outputs_by_case_id[case.id])
        for case in dataset.cases
    ]
    decision_total = sum(item.decision_total for item in reports)
    mapping_total = sum(item.mapping_total for item in reports)
    grouping_total = sum(item.grouping_pair_total for item in reports)
    return FieldDisambiguationEvaluationReport(
        rubric_version=M2_EVALUATION_RUBRIC_VERSION,
        dataset_version=dataset.dataset_version,
        dataset_review_status=dataset.review_status,
        quality_gate=(
            "blocked_pending_user_review"
            if dataset.review_status == "draft_user_review_required"
            else "measured_no_release_gate"
        ),
        pass_count=sum(item.status == "pass" for item in reports),
        fail_count=sum(item.status == "fail" for item in reports),
        decision_accuracy=_ratio(
            sum(item.decision_matched for item in reports), decision_total
        ),
        mapping_accuracy=_ratio(sum(item.mapping_matched for item in reports), mapping_total),
        semantic_grouping_accuracy=_ratio(
            sum(item.grouping_pair_matched for item in reports), grouping_total
        ),
        cases=reports,
    )


def load_field_disambiguation_outputs(
    path: Path,
) -> dict[str, FieldDisambiguationResult]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("m2_evaluation_outputs_must_be_object")
    return {
        case_id: FieldDisambiguationResult.model_validate(output)
        for case_id, output in raw.items()
    }


assert FIELD_DISAMBIGUATION_CONTRACT_VERSION == "field-disambiguation-contract-v1"
assert FIELD_DISAMBIGUATION_PROMPT_VERSION == "field-disambiguation-prompt-v1"
assert VISUAL_FIELD_CATALOG_VERSION == "visual-field-catalog-v1"
