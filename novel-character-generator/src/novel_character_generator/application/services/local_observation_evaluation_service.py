from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from novel_character_generator.application.ports.local_observation import (
    CoarseVisualFamily,
    EpistemicStatus,
    LocalObservationDiscoveryInput,
    LocalObservationDiscoveryResult,
    TemporalSignalKind,
    UnresolvedReasonCode,
)
from novel_character_generator.application.services.local_observation_service import (
    LocalObservationContractError,
    validate_local_observation_output,
)
from novel_character_generator.domain.policies.mention_kinds import MentionKind

M1_EVALUATION_DATASET_SCHEMA_VERSION: Literal[
    "local-observation-evaluation-dataset-v1"
] = "local-observation-evaluation-dataset-v1"
M1_EVALUATION_RUBRIC_VERSION: Literal[
    "local-observation-evaluation-rubric-v1"
] = "local-observation-evaluation-rubric-v1"


class ExpectedLocalEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    accepted_mentions: list[str] = Field(min_length=1)
    mention_kind: MentionKind


class ExpectedLocalFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    owner_key: str = Field(min_length=1)
    evidence_quotes: list[str] = Field(min_length=1)
    coarse_family: CoarseVisualFamily
    epistemic_status: EpistemicStatus
    proposition_concept_groups: list[list[str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_concept_groups(self) -> ExpectedLocalFact:
        if any(
            not group or any(not item for item in group)
            for group in self.proposition_concept_groups
        ):
            raise ValueError("empty_proposition_concept_group")
        return self


class ExpectedLocalSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    owner_key: str | None
    fact_key: str | None
    evidence_quotes: list[str] = Field(min_length=1)
    signal_kind: TemporalSignalKind


class ExpectedLocalUnresolved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    owner_key: str | None
    evidence_quotes: list[str] = Field(min_length=1)
    reason_code: UnresolvedReasonCode
    proposition_concept_groups: list[list[str]] = Field(default_factory=list)


class ForbiddenLocalFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)
    terms_any: list[str] = Field(min_length=1)
    coarse_family: CoarseVisualFamily | None = None


class LocalObservationExpectedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[ExpectedLocalEntity]
    required_facts: list[ExpectedLocalFact]
    allowed_facts: list[ExpectedLocalFact]
    temporal_signals: list[ExpectedLocalSignal]
    unresolved_items: list[ExpectedLocalUnresolved]
    forbidden_facts: list[ForbiddenLocalFact]
    allow_additional_facts: bool = False
    allow_additional_temporal_signals: bool = False
    allow_additional_unresolved_items: bool = False

    @model_validator(mode="after")
    def validate_expected_keys(self) -> LocalObservationExpectedOutput:
        entity_keys = [item.key for item in self.entities]
        fact_keys = [item.key for item in [*self.required_facts, *self.allowed_facts]]
        if len(entity_keys) != len(set(entity_keys)):
            raise ValueError("duplicate_expected_entity_key")
        if len(fact_keys) != len(set(fact_keys)):
            raise ValueError("duplicate_expected_fact_key")
        known_entities = set(entity_keys)
        known_facts = set(fact_keys)
        referenced_entities = {
            item.owner_key for item in [*self.required_facts, *self.allowed_facts]
        }
        referenced_entities.update(
            item.owner_key
            for item in self.temporal_signals
            if item.owner_key is not None
        )
        referenced_entities.update(
            item.owner_key
            for item in self.unresolved_items
            if item.owner_key is not None
        )
        if referenced_entities - known_entities:
            raise ValueError("unknown_expected_entity_key")
        if {
            item.fact_key
            for item in self.temporal_signals
            if item.fact_key is not None
        } - known_facts:
            raise ValueError("unknown_expected_fact_key")
        return self


class LocalObservationEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input: LocalObservationDiscoveryInput
    expected: LocalObservationExpectedOutput


class LocalObservationEvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["local-observation-evaluation-dataset-v1"]
    dataset_version: str = Field(min_length=1)
    node_contract_version: Literal["local-observation-contract-v1.1"]
    prompt_version: Literal["local-observation-discovery-prompt-v1.1"]
    review_status: Literal["draft_user_review_required", "approved"]
    review_notes: list[str]
    cases: list[LocalObservationEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> LocalObservationEvaluationDataset:
        case_ids = [item.id for item in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate_m1_evaluation_case_id")
        return self


class LocalObservationCaseEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    status: Literal["pass", "review", "fail"]
    errors: list[str]
    review_reasons: list[str]
    required_fact_total: int = Field(ge=0)
    required_fact_matched: int = Field(ge=0)
    actual_fact_total: int = Field(ge=0)
    supported_fact_total: int = Field(ge=0)
    quote_total: int = Field(ge=0)
    quote_valid: int = Field(ge=0)
    epistemic_total: int = Field(ge=0)
    epistemic_correct: int = Field(ge=0)
    temporal_total: int = Field(ge=0)
    temporal_matched: int = Field(ge=0)
    actual_temporal_total: int = Field(ge=0)
    unresolved_total: int = Field(ge=0)
    unresolved_matched: int = Field(ge=0)
    actual_unresolved_total: int = Field(ge=0)


class LocalObservationEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_version: Literal["local-observation-evaluation-rubric-v1"]
    dataset_version: str
    dataset_review_status: Literal["draft_user_review_required", "approved"]
    quality_gate: Literal["blocked_pending_user_review", "measured_no_release_gate"]
    pass_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    fail_count: int = Field(ge=0)
    required_fact_total: int = Field(ge=0)
    required_fact_matched: int = Field(ge=0)
    actual_fact_total: int = Field(ge=0)
    supported_fact_total: int = Field(ge=0)
    temporal_signal_total: int = Field(ge=0)
    temporal_signal_matched: int = Field(ge=0)
    actual_temporal_signal_total: int = Field(ge=0)
    unresolved_item_total: int = Field(ge=0)
    unresolved_item_matched: int = Field(ge=0)
    actual_unresolved_item_total: int = Field(ge=0)
    required_fact_recall: float = Field(ge=0, le=1)
    supported_fact_precision: float = Field(ge=0, le=1)
    quote_fidelity: float = Field(ge=0, le=1)
    epistemic_accuracy: float = Field(ge=0, le=1)
    temporal_signal_recall: float = Field(ge=0, le=1)
    temporal_signal_precision: float = Field(ge=0, le=1)
    unresolved_item_recall: float = Field(ge=0, le=1)
    unresolved_item_precision: float = Field(ge=0, le=1)
    cases: list[LocalObservationCaseEvaluation]


def load_local_observation_evaluation_dataset(
    path: Path,
) -> LocalObservationEvaluationDataset:
    return LocalObservationEvaluationDataset.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _entity_matches(
    entity_mentions: dict[str, tuple[str, str, MentionKind]],
    expected: ExpectedLocalEntity,
) -> set[str]:
    accepted = {_normalized(item) for item in expected.accepted_mentions}
    return {
        local_id
        for local_id, (mention, representative, mention_kind) in entity_mentions.items()
        if mention_kind == expected.mention_kind
        and ({_normalized(mention), _normalized(representative)} & accepted)
    }


def _concept_groups_match(value: str, groups: list[list[str]]) -> bool:
    normalized = _normalized(value)
    return all(any(_normalized(term) in normalized for term in group) for group in groups)


def evaluate_local_observation_case(
    case: LocalObservationEvaluationCase,
    output: LocalObservationDiscoveryResult,
) -> LocalObservationCaseEvaluation:
    errors: list[str] = []
    review_reasons: list[str] = []
    try:
        validate_local_observation_output(case.input, output)
    except LocalObservationContractError as error:
        errors.append(f"contract:{error.code}")

    entity_mentions = {
        item.local_entity_id: (
            item.mention_quote,
            item.representative_name,
            item.mention_kind,
        )
        for item in output.entities
    }
    entity_ids_by_key: dict[str, set[str]] = {}
    for expected_entity in case.expected.entities:
        matches = _entity_matches(entity_mentions, expected_entity)
        entity_ids_by_key[expected_entity.key] = matches
        if not matches:
            errors.append(f"missing_entity:{expected_entity.key}")

    quote_values = [item.mention_quote for item in output.entities]
    quote_values.extend(item.evidence_quote for item in output.facts)
    quote_values.extend(item.evidence_quote for item in output.temporal_signals)
    quote_values.extend(item.evidence_quote for item in output.unresolved_items)
    quote_valid = sum(item in case.input.chunk_text for item in quote_values)

    required = case.expected.required_facts
    expected_facts = [*required, *case.expected.allowed_facts]
    unmatched_expected = set(range(len(expected_facts)))
    matched_expected_to_actual: dict[str, str] = {}
    required_matched = 0
    supported_fact_total = 0
    epistemic_total = 0
    epistemic_correct = 0

    for fact in output.facts:
        match_index = next(
            (
                index
                for index in unmatched_expected
                if fact.entity_ref in entity_ids_by_key.get(expected_facts[index].owner_key, set())
                and fact.evidence_quote in expected_facts[index].evidence_quotes
                and fact.coarse_family == expected_facts[index].coarse_family
            ),
            None,
        )
        if match_index is None:
            rendered = f"{fact.evidence_quote} {fact.raw_proposition}"
            forbidden = next(
                (
                    item
                    for item in case.expected.forbidden_facts
                    if (item.coarse_family is None or item.coarse_family == fact.coarse_family)
                    and any(term in rendered for term in item.terms_any)
                ),
                None,
            )
            if forbidden is not None:
                errors.append(f"forbidden_fact:{forbidden.reason}:{fact.local_fact_id}")
            elif not case.expected.allow_additional_facts:
                errors.append(f"unexpected_fact:{fact.local_fact_id}")
            continue

        expected_fact = expected_facts[match_index]
        unmatched_expected.remove(match_index)
        supported_fact_total += 1
        matched_expected_to_actual[expected_fact.key] = fact.local_fact_id
        if match_index < len(required):
            required_matched += 1
        epistemic_total += 1
        if fact.epistemic_status == expected_fact.epistemic_status:
            epistemic_correct += 1
        else:
            errors.append(f"wrong_epistemic_status:{expected_fact.key}")
        if expected_fact.proposition_concept_groups and not _concept_groups_match(
            fact.raw_proposition, expected_fact.proposition_concept_groups
        ):
            review_reasons.append(f"proposition_wording:{expected_fact.key}")

    for index in sorted(unmatched_expected):
        if index < len(required):
            errors.append(f"missing_required_fact:{expected_facts[index].key}")

    temporal_matched = 0
    unmatched_signals = set(range(len(case.expected.temporal_signals)))
    for signal in output.temporal_signals:
        match_index = next(
            (
                index
                for index in unmatched_signals
                if signal.signal_kind == case.expected.temporal_signals[index].signal_kind
                and signal.evidence_quote
                in case.expected.temporal_signals[index].evidence_quotes
                and (
                    case.expected.temporal_signals[index].owner_key is None
                    or signal.entity_ref
                    in entity_ids_by_key.get(
                        case.expected.temporal_signals[index].owner_key or "", set()
                    )
                )
                and (
                    case.expected.temporal_signals[index].fact_key is None
                    or signal.fact_ref
                    == matched_expected_to_actual.get(
                        case.expected.temporal_signals[index].fact_key or ""
                    )
                )
            ),
            None,
        )
        if match_index is None:
            if not case.expected.allow_additional_temporal_signals:
                errors.append(f"unexpected_temporal_signal:{signal.local_signal_id}")
            continue
        unmatched_signals.remove(match_index)
        temporal_matched += 1
    for index in sorted(unmatched_signals):
        errors.append(f"missing_temporal_signal:{case.expected.temporal_signals[index].key}")

    unmatched_unresolved = set(range(len(case.expected.unresolved_items)))
    for item in output.unresolved_items:
        match_index = next(
            (
                index
                for index in unmatched_unresolved
                if item.reason_code == case.expected.unresolved_items[index].reason_code
                and item.evidence_quote
                in case.expected.unresolved_items[index].evidence_quotes
                and (
                    case.expected.unresolved_items[index].owner_key is None
                    or item.entity_ref
                    in entity_ids_by_key.get(
                        case.expected.unresolved_items[index].owner_key or "", set()
                    )
                )
            ),
            None,
        )
        if match_index is None:
            if not case.expected.allow_additional_unresolved_items:
                errors.append(f"unexpected_unresolved:{item.local_item_id}")
            continue
        expected_item = case.expected.unresolved_items[match_index]
        unmatched_unresolved.remove(match_index)
        if expected_item.proposition_concept_groups and not _concept_groups_match(
            item.raw_proposition, expected_item.proposition_concept_groups
        ):
            review_reasons.append(f"unresolved_wording:{expected_item.key}")
    for index in sorted(unmatched_unresolved):
        errors.append(f"missing_unresolved:{case.expected.unresolved_items[index].key}")
    unresolved_matched = len(case.expected.unresolved_items) - len(unmatched_unresolved)

    status: Literal["pass", "review", "fail"]
    if errors:
        status = "fail"
    elif review_reasons:
        status = "review"
    else:
        status = "pass"
    return LocalObservationCaseEvaluation(
        case_id=case.id,
        status=status,
        errors=errors,
        review_reasons=review_reasons,
        required_fact_total=len(required),
        required_fact_matched=required_matched,
        actual_fact_total=len(output.facts),
        supported_fact_total=supported_fact_total,
        quote_total=len(quote_values),
        quote_valid=quote_valid,
        epistemic_total=epistemic_total,
        epistemic_correct=epistemic_correct,
        temporal_total=len(case.expected.temporal_signals),
        temporal_matched=temporal_matched,
        actual_temporal_total=len(output.temporal_signals),
        unresolved_total=len(case.expected.unresolved_items),
        unresolved_matched=unresolved_matched,
        actual_unresolved_total=len(output.unresolved_items),
    )


def evaluate_local_observation_dataset(
    dataset: LocalObservationEvaluationDataset,
    outputs_by_case_id: dict[str, LocalObservationDiscoveryResult],
) -> LocalObservationEvaluationReport:
    unknown_outputs = sorted(set(outputs_by_case_id) - {case.id for case in dataset.cases})
    if unknown_outputs:
        raise ValueError(f"unknown_m1_evaluation_output:{','.join(unknown_outputs)}")
    missing_outputs = sorted({case.id for case in dataset.cases} - set(outputs_by_case_id))
    if missing_outputs:
        raise ValueError(f"missing_m1_evaluation_output:{','.join(missing_outputs)}")

    case_reports = [
        evaluate_local_observation_case(case, outputs_by_case_id[case.id])
        for case in dataset.cases
    ]
    required_total = sum(item.required_fact_total for item in case_reports)
    required_matched = sum(item.required_fact_matched for item in case_reports)
    actual_total = sum(item.actual_fact_total for item in case_reports)
    supported_total = sum(item.supported_fact_total for item in case_reports)
    quote_total = sum(item.quote_total for item in case_reports)
    quote_valid = sum(item.quote_valid for item in case_reports)
    epistemic_total = sum(item.epistemic_total for item in case_reports)
    epistemic_correct = sum(item.epistemic_correct for item in case_reports)
    temporal_total = sum(item.temporal_total for item in case_reports)
    temporal_matched = sum(item.temporal_matched for item in case_reports)
    actual_temporal_total = sum(item.actual_temporal_total for item in case_reports)
    unresolved_total = sum(item.unresolved_total for item in case_reports)
    unresolved_matched = sum(item.unresolved_matched for item in case_reports)
    actual_unresolved_total = sum(item.actual_unresolved_total for item in case_reports)
    return LocalObservationEvaluationReport(
        rubric_version=M1_EVALUATION_RUBRIC_VERSION,
        dataset_version=dataset.dataset_version,
        dataset_review_status=dataset.review_status,
        quality_gate=(
            "blocked_pending_user_review"
            if dataset.review_status == "draft_user_review_required"
            else "measured_no_release_gate"
        ),
        pass_count=sum(item.status == "pass" for item in case_reports),
        review_count=sum(item.status == "review" for item in case_reports),
        fail_count=sum(item.status == "fail" for item in case_reports),
        required_fact_total=required_total,
        required_fact_matched=required_matched,
        actual_fact_total=actual_total,
        supported_fact_total=supported_total,
        temporal_signal_total=temporal_total,
        temporal_signal_matched=temporal_matched,
        actual_temporal_signal_total=actual_temporal_total,
        unresolved_item_total=unresolved_total,
        unresolved_item_matched=unresolved_matched,
        actual_unresolved_item_total=actual_unresolved_total,
        required_fact_recall=_ratio(required_matched, required_total),
        supported_fact_precision=_ratio(supported_total, actual_total),
        quote_fidelity=_ratio(quote_valid, quote_total),
        epistemic_accuracy=_ratio(epistemic_correct, epistemic_total),
        temporal_signal_recall=_ratio(temporal_matched, temporal_total),
        temporal_signal_precision=_ratio(temporal_matched, actual_temporal_total),
        unresolved_item_recall=_ratio(unresolved_matched, unresolved_total),
        unresolved_item_precision=_ratio(unresolved_matched, actual_unresolved_total),
        cases=case_reports,
    )


def load_outputs_by_case_id(path: Path) -> dict[str, LocalObservationDiscoveryResult]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("m1_evaluation_outputs_must_be_object")
    return {
        case_id: LocalObservationDiscoveryResult.model_validate(output)
        for case_id, output in raw.items()
    }
