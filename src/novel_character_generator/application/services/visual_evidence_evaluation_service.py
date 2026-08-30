from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_character_generator.application.ports.visual_evidence import (
    GroundedEvidenceCandidate,
    VisualEvidenceDiscoveryInput,
    VisualEvidenceDiscoveryResult,
)
from novel_character_generator.application.services.visual_evidence_service import (
    VisualEvidenceContractError,
    validate_visual_evidence_output,
)
from novel_character_generator.domain.entities.document import TextChunk
from novel_character_generator.domain.policies.text_processing import (
    build_chunks,
    decode_text,
    detect_chapters,
    normalize_text,
)

M1_V2_EVALUATION_DATASET_SCHEMA_VERSION: Literal[
    "visual-evidence-evaluation-dataset-v2.4"
] = "visual-evidence-evaluation-dataset-v2.4"
M1_V2_EVALUATION_RUBRIC_VERSION: Literal[
    "visual-evidence-evaluation-rubric-v2.5"
] = "visual-evidence-evaluation-rubric-v2.5"
VisualEvidenceOwnerPolicy = Literal["required", "allowed", "must_be_null"]


class ExpectedVisualEvidenceOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    accepted_mentions: list[str] = Field(min_length=1)


class ExpectedVisualEvidenceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    owner_policy: VisualEvidenceOwnerPolicy
    owner_key: str | None = None
    evidence_quotes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_owner_policy(self) -> ExpectedVisualEvidenceCandidate:
        if self.owner_policy in {"required", "allowed"} and self.owner_key is None:
            raise ValueError("visual_evidence_owner_policy_requires_owner_key")
        if self.owner_policy == "must_be_null" and self.owner_key is not None:
            raise ValueError("must_be_null_visual_owner_cannot_reference_owner_key")
        return self


class ForbiddenVisualEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)
    terms_any: list[str] = Field(min_length=1)


class VisualEvidenceExpectedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owners: list[ExpectedVisualEvidenceOwner]
    required_candidates: list[ExpectedVisualEvidenceCandidate]
    allowed_candidates: list[ExpectedVisualEvidenceCandidate]
    forbidden_candidates: list[ForbiddenVisualEvidence]
    allow_additional_candidates: bool = False

    @model_validator(mode="after")
    def validate_expected_keys(self) -> VisualEvidenceExpectedOutput:
        owner_keys = [item.key for item in self.owners]
        candidate_keys = [
            item.key for item in [*self.required_candidates, *self.allowed_candidates]
        ]
        if len(owner_keys) != len(set(owner_keys)):
            raise ValueError("duplicate_expected_visual_owner_key")
        if len(candidate_keys) != len(set(candidate_keys)):
            raise ValueError("duplicate_expected_visual_candidate_key")
        known_owners = set(owner_keys)
        referenced = {
            item.owner_key
            for item in [*self.required_candidates, *self.allowed_candidates]
            if item.owner_key is not None
        }
        if referenced - known_owners:
            raise ValueError("unknown_expected_visual_owner_key")
        alias_owners: dict[str, str] = {}
        for owner in self.owners:
            for mention in owner.accepted_mentions:
                normalized = " ".join(mention.split()).casefold()
                previous = alias_owners.setdefault(normalized, owner.key)
                if previous != owner.key:
                    raise ValueError("ambiguous_expected_visual_owner_mention")
        return self


class VisualEvidenceSourceChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    chunk_tokens: int = Field(ge=1_000, le=12_000)
    chunk_ordinal: int = Field(ge=0)
    chapter_ordinal: int = Field(ge=0)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def require_project_relative_source(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("unsafe_visual_evidence_source_chunk_path")
        if path.parts[:2] != ("tests", "测试"):
            raise ValueError("visual_evidence_source_must_be_under_tests_real_chunks")
        return normalized


class VisualEvidenceEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    source_chunk: VisualEvidenceSourceChunk | None = None
    input: VisualEvidenceDiscoveryInput
    expected: VisualEvidenceExpectedOutput

    @model_validator(mode="after")
    def validate_expected_quotes(self) -> VisualEvidenceEvaluationCase:
        expected = [
            *self.expected.required_candidates,
            *self.expected.allowed_candidates,
        ]
        for candidate in expected:
            for quote in candidate.evidence_quotes:
                if quote not in self.input.chunk_text:
                    raise ValueError("expected_visual_quote_not_in_chunk")
                if self.input.chunk_text.count(quote) != 1:
                    raise ValueError("expected_visual_quote_not_uniquely_locatable")
        for owner in self.expected.owners:
            if any(mention not in self.input.chunk_text for mention in owner.accepted_mentions):
                raise ValueError("expected_visual_owner_mention_not_in_chunk")
        return self


class VisualEvidenceEvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[
        "visual-evidence-evaluation-dataset-v2.2",
        "visual-evidence-evaluation-dataset-v2.4",
    ]
    dataset_version: str = Field(min_length=1)
    node_contract_version: Literal["visual-evidence-contract-v2"]
    prompt_version: Literal["visual-evidence-discovery-prompt-v2.8"]
    review_status: Literal["draft_user_review_required", "approved"]
    review_notes: list[str]
    cases: list[VisualEvidenceEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> VisualEvidenceEvaluationDataset:
        ids = [item.id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_visual_evaluation_case_id")
        return self


class VisualEvidenceCaseEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    status: Literal["pass", "review", "fail"]
    errors: list[str]
    review_reasons: list[str]
    required_candidate_total: int = Field(ge=0)
    required_candidate_matched: int = Field(ge=0)
    actual_candidate_total: int = Field(ge=0)
    scored_actual_candidate_total: int = Field(ge=0)
    unscored_candidate_total: int = Field(ge=0)
    owner_required_total: int = Field(ge=0)
    owner_required_matched: int = Field(ge=0)
    owner_allowed_total: int = Field(ge=0)
    owner_allowed_matched: int = Field(ge=0)
    owner_must_be_null_total: int = Field(ge=0)
    owner_must_be_null_matched: int = Field(ge=0)
    actual_owner_binding_total: int = Field(ge=0)
    correct_owner_binding_total: int = Field(ge=0)
    actual_owner_mention_total: int = Field(ge=0)
    quote_total: int = Field(ge=0)
    quote_valid: int = Field(ge=0)


class VisualEvidenceEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_version: Literal["visual-evidence-evaluation-rubric-v2.5"]
    dataset_version: str
    dataset_review_status: Literal["draft_user_review_required", "approved"]
    quality_gate: Literal["blocked_pending_user_review", "measured_no_release_gate"]
    pass_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    fail_count: int = Field(ge=0)
    required_candidate_total: int = Field(ge=0)
    required_candidate_matched: int = Field(ge=0)
    actual_candidate_total: int = Field(ge=0)
    scored_actual_candidate_total: int = Field(ge=0)
    unscored_candidate_total: int = Field(ge=0)
    owner_required_total: int = Field(ge=0)
    owner_required_matched: int = Field(ge=0)
    owner_allowed_total: int = Field(ge=0)
    owner_allowed_matched: int = Field(ge=0)
    owner_must_be_null_total: int = Field(ge=0)
    owner_must_be_null_matched: int = Field(ge=0)
    actual_owner_binding_total: int = Field(ge=0)
    correct_owner_binding_total: int = Field(ge=0)
    actual_owner_mention_total: int = Field(ge=0)
    quote_total: int = Field(ge=0)
    quote_valid: int = Field(ge=0)
    evidence_coverage_recall: float = Field(ge=0, le=1)
    candidate_precision: float = Field(ge=0, le=1)
    quote_fidelity: float = Field(ge=0, le=1)
    owner_required_recall: float = Field(ge=0, le=1)
    owner_binding_precision: float = Field(ge=0, le=1)
    owner_must_be_null_accuracy: float = Field(ge=0, le=1)
    cases: list[VisualEvidenceCaseEvaluation]


def load_visual_evidence_evaluation_dataset(
    path: Path,
    *,
    project_root: Path | None = None,
) -> VisualEvidenceEvaluationDataset:
    dataset = VisualEvidenceEvaluationDataset.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if project_root is not None:
        validate_visual_evidence_source_chunks(dataset, project_root=project_root)
    return dataset


def validate_visual_evidence_source_chunks(
    dataset: VisualEvidenceEvaluationDataset,
    *,
    project_root: Path,
) -> None:
    chunk_cache: dict[tuple[str, int], list[TextChunk]] = {}
    resolved_root = project_root.resolve()
    for case in dataset.cases:
        source = case.source_chunk
        if source is None:
            continue
        cache_key = (source.path, source.chunk_tokens)
        if cache_key not in chunk_cache:
            source_path = (resolved_root / source.path).resolve()
            if not source_path.is_relative_to(resolved_root):
                raise ValueError("visual_evidence_source_escapes_project_root")
            raw_text, _encoding = decode_text(source_path.read_bytes())
            normalized = normalize_text(raw_text)
            chunk_cache[cache_key] = build_chunks(
                normalized,
                detect_chapters(normalized.text),
                target_tokens=source.chunk_tokens,
            )
        chunks = chunk_cache[cache_key]
        if source.chunk_ordinal >= len(chunks):
            raise ValueError("visual_evidence_source_chunk_ordinal_out_of_range")
        chunk = chunks[source.chunk_ordinal]
        if chunk.chapter_ordinal != source.chapter_ordinal:
            raise ValueError("visual_evidence_source_chapter_mismatch")
        if chunk.content_hash != source.text_sha256:
            raise ValueError("visual_evidence_source_hash_mismatch")
        if chunk.content != case.input.chunk_text:
            raise ValueError("visual_evidence_source_text_mismatch")


def load_outputs_by_case_id(path: Path) -> dict[str, VisualEvidenceDiscoveryResult]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("visual_evidence_outputs_must_be_object")
    result: dict[str, VisualEvidenceDiscoveryResult] = {}
    for case_id, value in raw.items():
        result[case_id] = VisualEvidenceDiscoveryResult.model_validate(value)
    return result


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _quote_match_rank(actual: str, expected_quotes: list[str]) -> int:
    normalized = _normalized(actual)
    if any(normalized == _normalized(expected) for expected in expected_quotes):
        return 2
    if any(_normalized(expected) in normalized for expected in expected_quotes):
        return 1
    return 0


def _owner_matches(
    output: VisualEvidenceDiscoveryResult,
    expected: ExpectedVisualEvidenceOwner,
) -> set[str]:
    accepted = {_normalized(item) for item in expected.accepted_mentions}
    return {
        mention.mention_id
        for mention in output.mentions
        if _normalized(mention.mention_quote) in accepted
    }


def _candidate_owner_matches(
    candidate: GroundedEvidenceCandidate,
    expected: ExpectedVisualEvidenceCandidate,
    owner_ids: dict[str, set[str]],
) -> bool:
    if expected.owner_policy == "must_be_null":
        return candidate.local_owner_id is None
    accepted = owner_ids.get(expected.owner_key or "", set())
    if expected.owner_policy == "required":
        return candidate.local_owner_id in accepted
    return candidate.local_owner_id is None or candidate.local_owner_id in accepted


def evaluate_visual_evidence_case(
    case: VisualEvidenceEvaluationCase,
    output: VisualEvidenceDiscoveryResult | None,
) -> VisualEvidenceCaseEvaluation:
    expected_candidates = [
        *case.expected.required_candidates,
        *case.expected.allowed_candidates,
    ]
    owner_required_total = sum(
        item.owner_policy == "required" for item in expected_candidates
    )
    owner_allowed_total = sum(
        item.owner_policy == "allowed" for item in expected_candidates
    )
    owner_must_be_null_total = sum(
        item.owner_policy == "must_be_null" for item in expected_candidates
    )
    if output is None:
        return VisualEvidenceCaseEvaluation(
            case_id=case.id,
            status="review",
            errors=["missing_output"],
            review_reasons=["model_output_not_available"],
            required_candidate_total=len(case.expected.required_candidates),
            required_candidate_matched=0,
            actual_candidate_total=0,
            scored_actual_candidate_total=0,
            unscored_candidate_total=0,
            owner_required_total=owner_required_total,
            owner_required_matched=0,
            owner_allowed_total=owner_allowed_total,
            owner_allowed_matched=0,
            owner_must_be_null_total=owner_must_be_null_total,
            owner_must_be_null_matched=0,
            actual_owner_binding_total=0,
            correct_owner_binding_total=0,
            actual_owner_mention_total=0,
            quote_total=0,
            quote_valid=0,
        )

    matched_required: set[str] = set()
    matched_allowed: set[str] = set()
    matched_actual_indices: set[int] = set()
    correct_owner_binding_indices: set[int] = set()
    errors: list[str] = []
    reviews: list[str] = []
    try:
        output = validate_visual_evidence_output(
            case.input.chunk_text,
            output,
            expected_chunk_id=case.input.chunk_id,
        )
    except VisualEvidenceContractError as error:
        errors.append(error.code)

    owner_ids = {owner.key: _owner_matches(output, owner) for owner in case.expected.owners}
    actual = output.evidence_candidates

    required_keys = {item.key for item in case.expected.required_candidates}
    for index, candidate in enumerate(actual):
        if case.input.chunk_text.count(candidate.evidence_quote) != 1:
            errors.append(f"evidence_quote_not_uniquely_locatable:{index}")
        compatible = [
            item
            for item in expected_candidates
            if item.key not in matched_required | matched_allowed
            and _candidate_owner_matches(candidate, item, owner_ids)
            and _quote_match_rank(candidate.evidence_quote, item.evidence_quotes) > 0
        ]
        if compatible:
            matched_actual_indices.add(index)
            for matched in compatible:
                if matched.key in required_keys:
                    matched_required.add(matched.key)
                else:
                    matched_allowed.add(matched.key)
            if candidate.local_owner_id is not None and any(
                item.owner_policy in {"required", "allowed"} for item in compatible
            ):
                correct_owner_binding_indices.add(index)
        else:
            for forbidden in case.expected.forbidden_candidates:
                if any(
                    term.casefold() in candidate.evidence_quote.casefold()
                    for term in forbidden.terms_any
                ):
                    errors.append(f"forbidden_candidate:{forbidden.reason}:{index}")
            if not case.expected.allow_additional_candidates:
                errors.append(f"unexpected_candidate:{index}")
            else:
                reviews.append(f"unscored_additional_candidate:{index}")

    for item in case.expected.required_candidates:
        if item.key not in matched_required:
            errors.append(f"missing_required_candidate:{item.key}")

    matched_keys = matched_required | matched_allowed
    owner_required_matched = sum(
        item.owner_policy == "required" and item.key in matched_keys
        for item in expected_candidates
    )
    owner_allowed_matched = sum(
        item.owner_policy == "allowed" and item.key in matched_keys
        for item in expected_candidates
    )
    owner_must_be_null_matched = sum(
        item.owner_policy == "must_be_null" and item.key in matched_keys
        for item in expected_candidates
    )
    correct_owner_binding_total = len(correct_owner_binding_indices)
    actual_owner_binding_total = sum(
        candidate.local_owner_id is not None for candidate in actual
    )
    quote_total = len(output.mentions) + len(actual)
    quote_valid = sum(
        item.mention_quote in case.input.chunk_text for item in output.mentions
    ) + sum(
        case.input.chunk_text.count(item.evidence_quote) == 1 for item in actual
    )
    if errors:
        status: Literal["pass", "review", "fail"] = "fail"
    elif reviews:
        status = "review"
    else:
        status = "pass"
    return VisualEvidenceCaseEvaluation(
        case_id=case.id,
        status=status,
        errors=list(dict.fromkeys(errors)),
        review_reasons=reviews,
        required_candidate_total=len(case.expected.required_candidates),
        required_candidate_matched=len(matched_required),
        actual_candidate_total=len(actual),
        scored_actual_candidate_total=len(matched_actual_indices),
        unscored_candidate_total=max(0, len(actual) - len(matched_actual_indices)),
        owner_required_total=owner_required_total,
        owner_required_matched=owner_required_matched,
        owner_allowed_total=owner_allowed_total,
        owner_allowed_matched=owner_allowed_matched,
        owner_must_be_null_total=owner_must_be_null_total,
        owner_must_be_null_matched=owner_must_be_null_matched,
        actual_owner_binding_total=actual_owner_binding_total,
        correct_owner_binding_total=correct_owner_binding_total,
        actual_owner_mention_total=len(output.mentions),
        quote_total=quote_total,
        quote_valid=quote_valid,
    )


def evaluate_visual_evidence_dataset(
    dataset: VisualEvidenceEvaluationDataset,
    outputs: dict[str, VisualEvidenceDiscoveryResult],
) -> VisualEvidenceEvaluationReport:
    cases = [evaluate_visual_evidence_case(case, outputs.get(case.id)) for case in dataset.cases]
    pass_count = sum(item.status == "pass" for item in cases)
    review_count = sum(item.status == "review" for item in cases)
    fail_count = sum(item.status == "fail" for item in cases)
    required_total = sum(item.required_candidate_total for item in cases)
    required_matched = sum(item.required_candidate_matched for item in cases)
    actual_total = sum(item.actual_candidate_total for item in cases)
    scored_total = sum(item.scored_actual_candidate_total for item in cases)
    unscored_total = sum(item.unscored_candidate_total for item in cases)
    owner_required_total = sum(item.owner_required_total for item in cases)
    owner_required_matched = sum(item.owner_required_matched for item in cases)
    owner_allowed_total = sum(item.owner_allowed_total for item in cases)
    owner_allowed_matched = sum(item.owner_allowed_matched for item in cases)
    owner_must_be_null_total = sum(item.owner_must_be_null_total for item in cases)
    owner_must_be_null_matched = sum(item.owner_must_be_null_matched for item in cases)
    actual_owner_binding_total = sum(item.actual_owner_binding_total for item in cases)
    correct_owner_binding_total = sum(item.correct_owner_binding_total for item in cases)
    actual_owner_mention_total = sum(item.actual_owner_mention_total for item in cases)
    quote_total = sum(item.quote_total for item in cases)
    quote_valid = sum(item.quote_valid for item in cases)
    return VisualEvidenceEvaluationReport(
        rubric_version=M1_V2_EVALUATION_RUBRIC_VERSION,
        dataset_version=dataset.dataset_version,
        dataset_review_status=dataset.review_status,
        quality_gate=(
            "blocked_pending_user_review"
            if dataset.review_status == "draft_user_review_required"
            else "measured_no_release_gate"
        ),
        pass_count=pass_count,
        review_count=review_count,
        fail_count=fail_count,
        required_candidate_total=required_total,
        required_candidate_matched=required_matched,
        actual_candidate_total=actual_total,
        scored_actual_candidate_total=scored_total,
        unscored_candidate_total=unscored_total,
        owner_required_total=owner_required_total,
        owner_required_matched=owner_required_matched,
        owner_allowed_total=owner_allowed_total,
        owner_allowed_matched=owner_allowed_matched,
        owner_must_be_null_total=owner_must_be_null_total,
        owner_must_be_null_matched=owner_must_be_null_matched,
        actual_owner_binding_total=actual_owner_binding_total,
        correct_owner_binding_total=correct_owner_binding_total,
        actual_owner_mention_total=actual_owner_mention_total,
        quote_total=quote_total,
        quote_valid=quote_valid,
        evidence_coverage_recall=_ratio(required_matched, required_total),
        candidate_precision=_ratio(scored_total, actual_total),
        quote_fidelity=_ratio(quote_valid, quote_total),
        owner_required_recall=_ratio(owner_required_matched, owner_required_total),
        owner_binding_precision=_ratio(
            correct_owner_binding_total, actual_owner_binding_total
        ),
        owner_must_be_null_accuracy=_ratio(
            owner_must_be_null_matched, owner_must_be_null_total
        ),
        cases=cases,
    )
