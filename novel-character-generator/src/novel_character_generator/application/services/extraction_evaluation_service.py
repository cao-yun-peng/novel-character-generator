from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from novel_character_generator.application.ports.extraction import (
    GroundedVisualExtractionResult,
    ObservationDraft,
)
from novel_character_generator.domain.policies.visual_fields import (
    canonical_field_path,
    is_visual_field,
    normalize_life_phase,
)

EvaluationStatus = Literal["pass", "needs_review", "fail"]
ValueMatchStatus = Literal[
    "canonical",
    "accepted",
    "unrecognized",
    "rejected",
    "missing",
    "unexpected",
]
EvidenceMatchStatus = Literal[
    "exact",
    "contained",
    "unrecognized",
    "ungrounded",
    "missing",
    "unexpected",
]
StructureKey = tuple[str, str, str, str | None]


def _stable_value(value: Any) -> str:
    if isinstance(value, str):
        value = unicodedata.normalize("NFKC", value).strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ExpectedVisualObservation(BaseModel):
    character_name: str
    field_path: str
    value: Any
    accepted_values: list[Any] = Field(default_factory=list)
    rejected_values: list[Any] = Field(default_factory=list)
    evidence_quote: str
    epistemic_status: str = "asserted"
    life_phase_key: str | None = None

    @model_validator(mode="after")
    def validate_value_boundaries(self) -> ExpectedVisualObservation:
        canonical = _stable_value(self.value)
        accepted = {_stable_value(value) for value in self.accepted_values}
        rejected = {_stable_value(value) for value in self.rejected_values}
        if canonical in rejected:
            raise ValueError("canonical_value_cannot_be_rejected")
        if accepted & rejected:
            raise ValueError("accepted_and_rejected_values_overlap")
        return self


class ExtractionSeedCase(BaseModel):
    id: str
    text: str
    expected_observations: list[ExpectedVisualObservation] = Field(default_factory=list)
    slice_tags: list[str] = Field(default_factory=list)
    severity: str = "normal"
    notes: str | None = None


class ExtractionSeedDataset(BaseModel):
    name: str
    version: str
    rubric_version: str
    cases: list[ExtractionSeedCase]


class ExtractionObservationScore(BaseModel):
    character_name: str
    field_path: str
    status: EvaluationStatus
    reason_codes: list[str] = Field(default_factory=list)
    expected_value: Any = None
    actual_value: Any = None
    value_match: ValueMatchStatus
    expected_evidence_quote: str | None = None
    actual_evidence_quote: str | None = None
    evidence_match: EvidenceMatchStatus


class ExtractionCaseScore(BaseModel):
    case_id: str
    status: EvaluationStatus
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float
    accepted_value_rate: float
    exact_evidence_rate: float
    compatible_evidence_rate: float
    needs_review_count: int
    failed_observation_count: int
    passed: bool
    observations: list[ExtractionObservationScore] = Field(default_factory=list)


class ExtractionDatasetScore(BaseModel):
    dataset_name: str
    dataset_version: str
    rubric_version: str
    case_count: int
    passed_case_count: int
    needs_review_case_count: int
    failed_case_count: int
    precision: float
    recall: float
    f1: float
    accepted_value_rate: float
    exact_evidence_rate: float
    compatible_evidence_rate: float
    cases: list[ExtractionCaseScore]


def load_extraction_seed_dataset(path: Path) -> ExtractionSeedDataset:
    return ExtractionSeedDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _structure_key(
    *,
    character_name: str,
    field_path: str,
    epistemic_status: str,
    life_phase_key: str | None,
) -> StructureKey:
    normalized_phase, _ = normalize_life_phase(life_phase_key, None)
    return (
        character_name.strip(),
        canonical_field_path(field_path, character_name=character_name),
        epistemic_status,
        normalized_phase,
    )


def _expected_structure_key(item: ExpectedVisualObservation) -> StructureKey:
    return _structure_key(
        character_name=item.character_name,
        field_path=item.field_path,
        epistemic_status=item.epistemic_status,
        life_phase_key=item.life_phase_key,
    )


def _actual_structure_key(item: ObservationDraft) -> StructureKey:
    return _structure_key(
        character_name=item.character_name,
        field_path=item.field_path,
        epistemic_status=item.epistemic_status,
        life_phase_key=item.life_phase_key,
    )


def _value_match(
    expected: ExpectedVisualObservation,
    actual_value: Any,
) -> ValueMatchStatus:
    actual = _stable_value(actual_value)
    if actual == _stable_value(expected.value):
        return "canonical"
    if actual in {_stable_value(value) for value in expected.accepted_values}:
        return "accepted"
    if actual in {_stable_value(value) for value in expected.rejected_values}:
        return "rejected"
    return "unrecognized"


def _evidence_match(
    case_text: str,
    expected_quote: str,
    actual_quote: str,
) -> EvidenceMatchStatus:
    if actual_quote not in case_text:
        return "ungrounded"
    if actual_quote == expected_quote:
        return "exact"
    if actual_quote in expected_quote or expected_quote in actual_quote:
        return "contained"
    return "unrecognized"


def _pair_rank(
    case_text: str,
    expected: ExpectedVisualObservation,
    actual: ObservationDraft,
) -> tuple[int, int]:
    value_rank = {
        "canonical": 3,
        "accepted": 2,
        "unrecognized": 1,
        "rejected": 0,
    }[_value_match(expected, actual.value)]
    evidence_rank = {
        "exact": 3,
        "contained": 2,
        "unrecognized": 1,
        "ungrounded": 0,
    }[_evidence_match(case_text, expected.evidence_quote, actual.evidence_quote)]
    return value_rank, evidence_rank


def _score_pair(
    case_text: str,
    expected: ExpectedVisualObservation,
    actual: ObservationDraft,
) -> ExtractionObservationScore:
    value_match = _value_match(expected, actual.value)
    evidence_match = _evidence_match(
        case_text,
        expected.evidence_quote,
        actual.evidence_quote,
    )
    reason_codes: list[str] = []
    status: EvaluationStatus = "pass"
    if value_match == "rejected":
        status = "fail"
        reason_codes.append("known_rejected_value")
    elif value_match == "unrecognized":
        status = "needs_review"
        reason_codes.append("unrecognized_value_variant")
    elif value_match == "accepted":
        reason_codes.append("accepted_value_variant")

    if evidence_match == "ungrounded":
        status = "fail"
        reason_codes.append("ungrounded_evidence")
    elif evidence_match == "unrecognized":
        if status != "fail":
            status = "needs_review"
        reason_codes.append("unrecognized_evidence_span")
    elif evidence_match == "contained":
        reason_codes.append("compatible_evidence_span")

    return ExtractionObservationScore(
        character_name=expected.character_name,
        field_path=canonical_field_path(
            expected.field_path,
            character_name=expected.character_name,
        ),
        status=status,
        reason_codes=reason_codes,
        expected_value=expected.value,
        actual_value=actual.value,
        value_match=value_match,
        expected_evidence_quote=expected.evidence_quote,
        actual_evidence_quote=actual.evidence_quote,
        evidence_match=evidence_match,
    )


def _pair_group(
    case_text: str,
    expected: list[ExpectedVisualObservation],
    actual: list[ObservationDraft],
) -> tuple[
    list[tuple[ExpectedVisualObservation, ObservationDraft]],
    list[ExpectedVisualObservation],
    list[ObservationDraft],
]:
    candidates = sorted(
        (
            (_pair_rank(case_text, expected_item, actual_item), expected_index, actual_index)
            for expected_index, expected_item in enumerate(expected)
            for actual_index, actual_item in enumerate(actual)
        ),
        reverse=True,
    )
    used_expected: set[int] = set()
    used_actual: set[int] = set()
    pairs: list[tuple[ExpectedVisualObservation, ObservationDraft]] = []
    for _, expected_index, actual_index in candidates:
        if expected_index in used_expected or actual_index in used_actual:
            continue
        used_expected.add(expected_index)
        used_actual.add(actual_index)
        pairs.append((expected[expected_index], actual[actual_index]))
    missing = [item for index, item in enumerate(expected) if index not in used_expected]
    unexpected = [item for index, item in enumerate(actual) if index not in used_actual]
    return pairs, missing, unexpected


def _missing_score(expected: ExpectedVisualObservation) -> ExtractionObservationScore:
    return ExtractionObservationScore(
        character_name=expected.character_name,
        field_path=canonical_field_path(
            expected.field_path,
            character_name=expected.character_name,
        ),
        status="fail",
        reason_codes=["missing_observation"],
        expected_value=expected.value,
        value_match="missing",
        expected_evidence_quote=expected.evidence_quote,
        evidence_match="missing",
    )


def _unexpected_score(actual: ObservationDraft) -> ExtractionObservationScore:
    return ExtractionObservationScore(
        character_name=actual.character_name,
        field_path=canonical_field_path(
            actual.field_path,
            character_name=actual.character_name,
        ),
        status="fail",
        reason_codes=["unexpected_observation"],
        actual_value=actual.value,
        value_match="unexpected",
        actual_evidence_quote=actual.evidence_quote,
        evidence_match="unexpected",
    )


def evaluate_extraction_case(
    case: ExtractionSeedCase,
    actual: GroundedVisualExtractionResult,
) -> ExtractionCaseScore:
    for expected in case.expected_observations:
        if expected.evidence_quote not in case.text:
            raise ValueError(f"seed_expected_evidence_not_found:{case.id}")

    expected_groups: dict[StructureKey, list[ExpectedVisualObservation]] = defaultdict(list)
    actual_groups: dict[StructureKey, list[ObservationDraft]] = defaultdict(list)
    for expected in case.expected_observations:
        expected_groups[_expected_structure_key(expected)].append(expected)
    for observation in actual.observations:
        if is_visual_field(observation.field_path):
            actual_groups[_actual_structure_key(observation)].append(observation)

    observation_scores: list[ExtractionObservationScore] = []
    true_positive = 0
    false_positive = 0
    false_negative = 0
    for key in sorted(set(expected_groups) | set(actual_groups), key=repr):
        pairs, missing, unexpected = _pair_group(
            case.text,
            expected_groups.get(key, []),
            actual_groups.get(key, []),
        )
        true_positive += len(pairs)
        false_negative += len(missing)
        false_positive += len(unexpected)
        observation_scores.extend(
            _score_pair(case.text, expected, observation) for expected, observation in pairs
        )
        observation_scores.extend(_missing_score(expected) for expected in missing)
        observation_scores.extend(_unexpected_score(observation) for observation in unexpected)

    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 1.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    expected_count = len(case.expected_observations)
    accepted_values = sum(
        score.value_match in {"canonical", "accepted"} for score in observation_scores
    )
    exact_evidence = sum(score.evidence_match == "exact" for score in observation_scores)
    compatible_evidence = sum(
        score.evidence_match in {"exact", "contained"} for score in observation_scores
    )
    no_expected_success = not expected_count and not observation_scores
    accepted_value_rate = (
        accepted_values / expected_count if expected_count else float(no_expected_success)
    )
    exact_evidence_rate = (
        exact_evidence / expected_count if expected_count else float(no_expected_success)
    )
    compatible_evidence_rate = (
        compatible_evidence / expected_count if expected_count else float(no_expected_success)
    )
    needs_review_count = sum(score.status == "needs_review" for score in observation_scores)
    failed_observation_count = sum(score.status == "fail" for score in observation_scores)
    status: EvaluationStatus
    if failed_observation_count:
        status = "fail"
    elif needs_review_count:
        status = "needs_review"
    else:
        status = "pass"
    return ExtractionCaseScore(
        case_id=case.id,
        status=status,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=f1,
        accepted_value_rate=accepted_value_rate,
        exact_evidence_rate=exact_evidence_rate,
        compatible_evidence_rate=compatible_evidence_rate,
        needs_review_count=needs_review_count,
        failed_observation_count=failed_observation_count,
        passed=status == "pass",
        observations=observation_scores,
    )


def evaluate_extraction_dataset(
    dataset: ExtractionSeedDataset,
    actual_by_case_id: dict[str, GroundedVisualExtractionResult],
) -> ExtractionDatasetScore:
    missing = sorted({case.id for case in dataset.cases} - set(actual_by_case_id))
    if missing:
        raise ValueError(f"missing_seed_case_outputs:{','.join(missing)}")
    case_scores = [
        evaluate_extraction_case(case, actual_by_case_id[case.id])
        for case in dataset.cases
    ]
    true_positive = sum(item.true_positive for item in case_scores)
    false_positive = sum(item.false_positive for item in case_scores)
    false_negative = sum(item.false_negative for item in case_scores)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 1.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    expected_count = sum(len(case.expected_observations) for case in dataset.cases)
    observation_scores = [score for case in case_scores for score in case.observations]
    no_expected_success = not expected_count and all(case.status == "pass" for case in case_scores)
    accepted_value_rate = (
        sum(score.value_match in {"canonical", "accepted"} for score in observation_scores)
        / expected_count
        if expected_count
        else float(no_expected_success)
    )
    exact_evidence_rate = (
        sum(score.evidence_match == "exact" for score in observation_scores) / expected_count
        if expected_count
        else float(no_expected_success)
    )
    compatible_evidence_rate = (
        sum(
            score.evidence_match in {"exact", "contained"}
            for score in observation_scores
        )
        / expected_count
        if expected_count
        else float(no_expected_success)
    )
    return ExtractionDatasetScore(
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        rubric_version=dataset.rubric_version,
        case_count=len(case_scores),
        passed_case_count=sum(item.status == "pass" for item in case_scores),
        needs_review_case_count=sum(
            item.status == "needs_review" for item in case_scores
        ),
        failed_case_count=sum(item.status == "fail" for item in case_scores),
        precision=precision,
        recall=recall,
        f1=f1,
        accepted_value_rate=accepted_value_rate,
        exact_evidence_rate=exact_evidence_rate,
        compatible_evidence_rate=compatible_evidence_rate,
        cases=case_scores,
    )
