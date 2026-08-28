from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from novel_character_generator.application.ports.entity_resolution import GroundedCandidatePacket
from novel_character_generator.application.ports.extraction import (
    GroundedVisualExtractionResult,
    ObservationDraft,
    VisualCandidateExtractionResult,
)
from novel_character_generator.domain.policies.mention_kinds import MentionKind
from novel_character_generator.domain.policies.visual_fields import (
    canonical_field_path,
    is_visual_field,
    normalize_life_phase,
    visual_field_semantic_issue,
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
    "rejected",
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
    accepted_character_names: list[str] = Field(default_factory=list)
    field_path: str
    value: Any
    accepted_values: list[Any] = Field(default_factory=list)
    rejected_values: list[Any] = Field(default_factory=list)
    evidence_quote: str
    accepted_evidence_quotes: list[str] = Field(default_factory=list)
    rejected_evidence_quotes: list[str] = Field(default_factory=list)
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
        accepted_evidence = {item for item in self.accepted_evidence_quotes}
        rejected_evidence = {item for item in self.rejected_evidence_quotes}
        if self.evidence_quote in rejected_evidence:
            raise ValueError("canonical_evidence_cannot_be_rejected")
        if accepted_evidence & rejected_evidence:
            raise ValueError("accepted_and_rejected_evidence_overlap")
        return self


class ForbiddenVisualObservation(BaseModel):
    character_name: str | None = None
    accepted_character_names: list[str] = Field(default_factory=list)
    field_path: str
    values: list[Any] = Field(default_factory=list)
    epistemic_status: str | None = None
    life_phase_key: str | None = None
    reason: str = Field(min_length=1)


class ExpectedMention(BaseModel):
    surface: str = Field(min_length=1)
    accepted_surfaces: list[str] = Field(default_factory=list)
    mention_kind: MentionKind
    min_count: int = Field(default=1, ge=0)
    max_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_count_range(self) -> ExpectedMention:
        if self.max_count is not None and self.max_count < self.min_count:
            raise ValueError("mention_max_count_below_min_count")
        return self


class ExpectedDeferredItem(BaseModel):
    reason_code: str = Field(min_length=1)
    evidence_quote: str | None = None
    accepted_evidence_quotes: list[str] = Field(default_factory=list)
    min_count: int = Field(default=1, ge=0)
    max_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_count_range(self) -> ExpectedDeferredItem:
        if self.max_count is not None and self.max_count < self.min_count:
            raise ValueError("deferred_max_count_below_min_count")
        return self


class ExpectedTemporalSignal(BaseModel):
    kind: str = Field(min_length=1)
    label: str = Field(min_length=1)
    accepted_labels: list[str] = Field(default_factory=list)
    evidence_quote: str
    accepted_evidence_quotes: list[str] = Field(default_factory=list)
    character_name: str | None = None
    accepted_character_names: list[str] = Field(default_factory=list)


class ExtractionSeedCase(BaseModel):
    id: str
    text: str
    expected_observations: list[ExpectedVisualObservation] = Field(default_factory=list)
    required_observations: list[ExpectedVisualObservation] = Field(default_factory=list)
    allowed_observations: list[ExpectedVisualObservation] = Field(default_factory=list)
    forbidden_observations: list[ForbiddenVisualObservation] = Field(default_factory=list)
    expected_mentions: list[ExpectedMention] = Field(default_factory=list)
    expected_deferred_items: list[ExpectedDeferredItem] = Field(default_factory=list)
    allowed_deferred_items: list[ExpectedDeferredItem] = Field(default_factory=list)
    expected_temporal_signals: list[ExpectedTemporalSignal] = Field(default_factory=list)
    allow_unlisted_observations: bool = False
    allow_unlisted_deferred: bool = False
    allow_unlisted_temporal_signals: bool = False
    slice_tags: list[str] = Field(default_factory=list)
    severity: str = "normal"
    notes: str | None = None

    @model_validator(mode="after")
    def validate_rubric_shapes(self) -> ExtractionSeedCase:
        if self.expected_observations and self.required_observations:
            raise ValueError("legacy_and_required_observations_are_mutually_exclusive")
        return self

    @property
    def effective_required_observations(self) -> list[ExpectedVisualObservation]:
        return self.required_observations or self.expected_observations


class ExtractionSeedDataset(BaseModel):
    name: str
    version: str
    rubric_version: str
    cases: list[ExtractionSeedCase]

    @model_validator(mode="after")
    def validate_dataset_contract(self) -> ExtractionSeedDataset:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate_seed_case_id")
        for case in self.cases:
            if self.rubric_version.startswith("visual-observation-seed-v3") and (
                case.expected_observations
            ):
                raise ValueError(f"v3_forbids_legacy_expected_observations:{case.id}")
            observations = [
                *case.effective_required_observations,
                *case.allowed_observations,
            ]
            for observation in observations:
                canonical_path = canonical_field_path(
                    observation.field_path,
                    character_name=observation.character_name,
                )
                if not is_visual_field(canonical_path):
                    raise ValueError(
                        f"seed_expected_non_visual_field:{case.id}:{canonical_path}"
                    )
                semantic_issue = visual_field_semantic_issue(
                    canonical_path,
                    observation.value,
                    observation.evidence_quote,
                )
                if semantic_issue is not None:
                    raise ValueError(
                        f"seed_expected_field_semantic_issue:{case.id}:"
                        f"{canonical_path}:{semantic_issue}"
                    )
                quotes = [
                    observation.evidence_quote,
                    *observation.accepted_evidence_quotes,
                ]
                if any(quote not in case.text for quote in quotes):
                    raise ValueError(f"seed_expected_evidence_not_found:{case.id}")
            mention_surfaces = [
                surface
                for item in case.expected_mentions
                for surface in [item.surface, *item.accepted_surfaces]
            ]
            if any(surface not in case.text for surface in mention_surfaces):
                raise ValueError(f"seed_expected_mention_not_found:{case.id}")
            for deferred_item in [
                *case.expected_deferred_items,
                *case.allowed_deferred_items,
            ]:
                quotes = [
                    quote
                    for quote in [
                        deferred_item.evidence_quote,
                        *deferred_item.accepted_evidence_quotes,
                    ]
                    if quote is not None
                ]
                if any(quote not in case.text for quote in quotes):
                    raise ValueError(f"seed_expected_deferred_evidence_not_found:{case.id}")
            for temporal_item in case.expected_temporal_signals:
                quotes = [
                    temporal_item.evidence_quote,
                    *temporal_item.accepted_evidence_quotes,
                ]
                if any(quote not in case.text for quote in quotes):
                    raise ValueError(f"seed_expected_temporal_evidence_not_found:{case.id}")
        return self


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
    allowed_observation_count: int = 0
    unlisted_observation_count: int = 0
    forbidden_observation_count: int = 0
    mention_failure_count: int = 0
    deferred_failure_count: int = 0
    temporal_failure_count: int = 0
    duplicate_temporal_signal_count: int = 0
    asserted_deferred_collision_count: int = 0
    contract_reason_codes: list[str] = Field(default_factory=list)
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
    allowed_observation_count: int = 0
    unlisted_observation_count: int = 0
    forbidden_observation_count: int = 0
    mention_failure_count: int = 0
    deferred_failure_count: int = 0
    temporal_failure_count: int = 0
    duplicate_temporal_signal_count: int = 0
    asserted_deferred_collision_count: int = 0
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


def _expected_owner_names(item: ExpectedVisualObservation) -> set[str]:
    return {
        item.character_name.strip(),
        *(name.strip() for name in item.accepted_character_names),
    }


def _structure_compatible(
    expected: ExpectedVisualObservation,
    actual: ObservationDraft,
) -> bool:
    expected_key = _expected_structure_key(expected)
    actual_key = _actual_structure_key(actual)
    return (
        actual.character_name.strip() in _expected_owner_names(expected)
        and actual_key[1:] == expected_key[1:]
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
    expected: ExpectedVisualObservation,
    actual_quote: str,
) -> EvidenceMatchStatus:
    if actual_quote not in case_text:
        return "ungrounded"
    if actual_quote in expected.rejected_evidence_quotes:
        return "rejected"
    if actual_quote == expected.evidence_quote or actual_quote in expected.accepted_evidence_quotes:
        return "exact"
    accepted_quotes = [expected.evidence_quote, *expected.accepted_evidence_quotes]
    if any(actual_quote in quote or quote in actual_quote for quote in accepted_quotes):
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
        "rejected": 0,
        "ungrounded": 0,
    }[_evidence_match(case_text, expected, actual.evidence_quote)]
    return value_rank, evidence_rank


def _score_pair(
    case_text: str,
    expected: ExpectedVisualObservation,
    actual: ObservationDraft,
) -> ExtractionObservationScore:
    value_match = _value_match(expected, actual.value)
    evidence_match = _evidence_match(
        case_text,
        expected,
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

    if evidence_match == "rejected":
        status = "fail"
        reason_codes.append("known_rejected_evidence")
    elif evidence_match == "ungrounded":
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
            if (
                _value_match(expected_item, actual_item.value) != "unrecognized"
                or _evidence_match(
                    case_text,
                    expected_item,
                    actual_item.evidence_quote,
                )
                != "unrecognized"
            )
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


def _forbidden_matches(
    forbidden: ForbiddenVisualObservation,
    actual: ObservationDraft,
) -> bool:
    accepted_owners = {
        *([forbidden.character_name.strip()] if forbidden.character_name else []),
        *(name.strip() for name in forbidden.accepted_character_names),
    }
    if accepted_owners and actual.character_name.strip() not in accepted_owners:
        return False
    if canonical_field_path(
        actual.field_path, character_name=actual.character_name
    ) != canonical_field_path(
        forbidden.field_path, character_name=forbidden.character_name
    ):
        return False
    if forbidden.epistemic_status is not None and (
        actual.epistemic_status != forbidden.epistemic_status
    ):
        return False
    expected_phase, _ = normalize_life_phase(forbidden.life_phase_key, None)
    actual_phase, _ = normalize_life_phase(actual.life_phase_key, None)
    if forbidden.life_phase_key is not None and actual_phase != expected_phase:
        return False
    if forbidden.values and _stable_value(actual.value) not in {
        _stable_value(value) for value in forbidden.values
    }:
        return False
    return True


def _forbidden_score(
    actual: ObservationDraft,
    forbidden: ForbiddenVisualObservation,
) -> ExtractionObservationScore:
    score = _unexpected_score(actual)
    score.reason_codes = ["forbidden_observation", forbidden.reason]
    return score


def _pair_allowed_group(
    case_text: str,
    expected: list[ExpectedVisualObservation],
    actual: list[ObservationDraft],
) -> tuple[int, list[ObservationDraft]]:
    pairs, _, unexpected = _pair_group(case_text, expected, actual)
    allowed_count = 0
    remaining = list(unexpected)
    for expected_item, actual_item in pairs:
        score = _score_pair(case_text, expected_item, actual_item)
        if score.status == "pass":
            allowed_count += 1
        else:
            remaining.append(actual_item)
    return allowed_count, remaining


def _score_mentions(
    case: ExtractionSeedCase,
    actual: GroundedVisualExtractionResult,
    packet: GroundedCandidatePacket | None,
    candidates: VisualCandidateExtractionResult | None,
) -> tuple[int, list[str]]:
    if not case.expected_mentions:
        return 0, []
    if candidates is not None:
        mentions = [
            (item.mention_quote, item.mention_kind)
            for item in candidates.entities
            if item.mention_quote in case.text
        ]
    elif packet is not None:
        mentions = [(item.mention_text, item.mention_kind) for item in packet.mentions]
    else:
        mentions = [(item.text, item.kind) for item in actual.mentions]
    failures = 0
    reasons: list[str] = []
    for expected in case.expected_mentions:
        expected_failed = False
        accepted_surfaces = {expected.surface, *expected.accepted_surfaces}
        count = sum(
            surface in accepted_surfaces and kind == expected.mention_kind
            for surface, kind in mentions
        )
        if count < expected.min_count:
            expected_failed = True
            reasons.append(
                f"missing_mention:{expected.surface}:{expected.mention_kind}:{count}"
            )
        if expected.max_count is not None and count > expected.max_count:
            expected_failed = True
            reasons.append(
                f"excess_mention:{expected.surface}:{expected.mention_kind}:{count}"
            )
        wrong_kinds = sorted(
            {kind for surface, kind in mentions if surface in accepted_surfaces}
            - {expected.mention_kind}
        )
        if wrong_kinds:
            expected_failed = True
            reasons.append(
                f"wrong_mention_kind:{expected.surface}:{','.join(wrong_kinds)}"
            )
        failures += expected_failed
    return failures, reasons


def _deferred_matches(expected: ExpectedDeferredItem, actual: Any) -> bool:
    if actual.reason_code != expected.reason_code:
        return False
    if expected.evidence_quote is None:
        return True
    return actual.evidence_quote in {
        expected.evidence_quote,
        *expected.accepted_evidence_quotes,
    }


def _score_deferred(
    case: ExtractionSeedCase,
    candidates: VisualCandidateExtractionResult | None,
) -> tuple[int, list[str]]:
    if candidates is None:
        if case.expected_deferred_items:
            raise ValueError(f"candidate_output_required_for_deferred_scoring:{case.id}")
        return 0, []
    actual_items = candidates.deferred_items
    failures = 0
    reasons: list[str] = []
    matched_indexes: set[int] = set()
    for expected in case.expected_deferred_items:
        indexes = [
            index
            for index, item in enumerate(actual_items)
            if _deferred_matches(expected, item)
        ]
        matched_indexes.update(indexes)
        count = len(indexes)
        if count < expected.min_count:
            failures += 1
            reasons.append(
                f"missing_deferred:{expected.reason_code}:{expected.evidence_quote or '*'}:{count}"
            )
        if expected.max_count is not None and count > expected.max_count:
            failures += 1
            reasons.append(
                f"excess_deferred:{expected.reason_code}:{expected.evidence_quote or '*'}:{count}"
            )
    for allowed in case.allowed_deferred_items:
        matched_indexes.update(
            index
            for index, item in enumerate(actual_items)
            if _deferred_matches(allowed, item)
        )
    if not case.allow_unlisted_deferred:
        unlisted = [
            index for index in range(len(actual_items)) if index not in matched_indexes
        ]
        if unlisted:
            failures += len(unlisted)
            reasons.extend(f"unexpected_deferred:{index}" for index in unlisted)
    return failures, reasons


def _score_temporal_signals(
    case: ExtractionSeedCase,
    packet: GroundedCandidatePacket | None,
) -> tuple[int, list[str], int]:
    if packet is None:
        if case.expected_temporal_signals:
            raise ValueError(f"grounded_packet_required_for_temporal_scoring:{case.id}")
        return 0, [], 0
    mention_names = {
        item.mention_id: item.representative_name for item in packet.mentions
    }
    actual = []
    seen_temporal: set[tuple[str | None, str, str, str]] = set()
    duplicate_count = 0
    for item in packet.temporal_signals:
        key = (
            item.mention_id,
            item.kind,
            unicodedata.normalize("NFKC", item.label).strip(),
            unicodedata.normalize("NFKC", item.evidence_quote).strip(),
        )
        if key in seen_temporal:
            duplicate_count += 1
            continue
        seen_temporal.add(key)
        actual.append(item)
    failures = 0
    reasons: list[str] = []
    matched_indexes: set[int] = set()
    for expected in case.expected_temporal_signals:
        accepted_labels = {expected.label, *expected.accepted_labels}
        accepted_quotes = {
            expected.evidence_quote,
            *expected.accepted_evidence_quotes,
        }
        accepted_owners = {
            *([expected.character_name] if expected.character_name else []),
            *expected.accepted_character_names,
        }
        index = next(
            (
                item_index
                for item_index, item in enumerate(actual)
                if item_index not in matched_indexes
                and item.kind == expected.kind
                and item.label in accepted_labels
                and any(
                    item.evidence_quote in quote or quote in item.evidence_quote
                    for quote in accepted_quotes
                )
                and (
                    not accepted_owners
                    or (
                        item.mention_id is not None
                        and mention_names.get(item.mention_id) in accepted_owners
                    )
                )
            ),
            None,
        )
        if index is None:
            failures += 1
            reasons.append(
                f"missing_temporal_signal:{expected.kind}:{expected.label}"
            )
        else:
            matched_indexes.add(index)
    if not case.allow_unlisted_temporal_signals:
        unlisted = [index for index in range(len(actual)) if index not in matched_indexes]
        if unlisted:
            failures += len(unlisted)
            reasons.extend(f"unexpected_temporal_signal:{index}" for index in unlisted)
    return failures, reasons, duplicate_count


def _asserted_deferred_collisions(
    candidates: VisualCandidateExtractionResult | None,
) -> list[str]:
    if candidates is None:
        return []
    asserted_quotes = {
        item.evidence_quote
        for item in candidates.visual_candidates
        if item.epistemic_status == "asserted"
    }
    deferred_quotes = {
        item.evidence_quote
        for item in candidates.deferred_items
        if item.evidence_quote is not None
    }
    return sorted(asserted_quotes & deferred_quotes)


def evaluate_extraction_case(
    case: ExtractionSeedCase,
    actual: GroundedVisualExtractionResult,
    *,
    candidates: VisualCandidateExtractionResult | None = None,
    packet: GroundedCandidatePacket | None = None,
) -> ExtractionCaseScore:
    required_observations = case.effective_required_observations
    for expected in [*required_observations, *case.allowed_observations]:
        if expected.evidence_quote not in case.text:
            raise ValueError(f"seed_expected_evidence_not_found:{case.id}")
        if any(quote not in case.text for quote in expected.accepted_evidence_quotes):
            raise ValueError(f"seed_accepted_evidence_not_found:{case.id}")

    expected_groups: dict[StructureKey, list[ExpectedVisualObservation]] = defaultdict(list)
    allowed_groups: dict[StructureKey, list[ExpectedVisualObservation]] = defaultdict(list)
    actual_groups: dict[StructureKey, list[ObservationDraft]] = defaultdict(list)
    for expected in required_observations:
        expected_groups[_expected_structure_key(expected)].append(expected)
    for allowed in case.allowed_observations:
        allowed_groups[_expected_structure_key(allowed)].append(allowed)
    reference_observations = [*required_observations, *case.allowed_observations]
    for observation in actual.observations:
        if is_visual_field(observation.field_path):
            compatible_keys = {
                _expected_structure_key(expected)
                for expected in reference_observations
                if _structure_compatible(expected, observation)
            }
            key = (
                next(iter(compatible_keys))
                if len(compatible_keys) == 1
                else _actual_structure_key(observation)
            )
            actual_groups[key].append(observation)

    observation_scores: list[ExtractionObservationScore] = []
    true_positive = 0
    false_positive = 0
    false_negative = 0
    allowed_observation_count = 0
    unlisted_observation_count = 0
    forbidden_observation_count = 0
    for key in sorted(set(expected_groups) | set(allowed_groups) | set(actual_groups), key=repr):
        pairs, missing, unexpected = _pair_group(
            case.text,
            expected_groups.get(key, []),
            actual_groups.get(key, []),
        )
        true_positive += len(pairs)
        false_negative += len(missing)
        observation_scores.extend(
            _score_pair(case.text, expected, observation) for expected, observation in pairs
        )
        observation_scores.extend(_missing_score(expected) for expected in missing)
        allowed_count, remaining = _pair_allowed_group(
            case.text,
            allowed_groups.get(key, []),
            unexpected,
        )
        allowed_observation_count += allowed_count
        ignored_in_group = 0
        for observation in remaining:
            forbidden = next(
                (
                    item
                    for item in case.forbidden_observations
                    if _forbidden_matches(item, observation)
                ),
                None,
            )
            if forbidden is not None:
                forbidden_observation_count += 1
                observation_scores.append(_forbidden_score(observation, forbidden))
            elif case.allow_unlisted_observations:
                unlisted_observation_count += 1
                ignored_in_group += 1
            else:
                observation_scores.append(_unexpected_score(observation))
        false_positive += len(remaining) - ignored_in_group

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
    expected_count = len(required_observations)
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
    mention_failure_count, mention_reasons = _score_mentions(
        case,
        actual,
        packet,
        candidates,
    )
    deferred_failure_count, deferred_reasons = _score_deferred(case, candidates)
    (
        temporal_failure_count,
        temporal_reasons,
        duplicate_temporal_signal_count,
    ) = _score_temporal_signals(case, packet)
    collision_quotes = _asserted_deferred_collisions(candidates)
    asserted_deferred_collision_count = len(collision_quotes)
    collision_reasons = [
        f"asserted_deferred_collision:{quote}" for quote in collision_quotes
    ]
    contract_reason_codes = [
        *mention_reasons,
        *deferred_reasons,
        *temporal_reasons,
        *collision_reasons,
    ]
    status: EvaluationStatus
    if (
        failed_observation_count
        or mention_failure_count
        or deferred_failure_count
        or temporal_failure_count
        or asserted_deferred_collision_count
    ):
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
        allowed_observation_count=allowed_observation_count,
        unlisted_observation_count=unlisted_observation_count,
        forbidden_observation_count=forbidden_observation_count,
        mention_failure_count=mention_failure_count,
        deferred_failure_count=deferred_failure_count,
        temporal_failure_count=temporal_failure_count,
        duplicate_temporal_signal_count=duplicate_temporal_signal_count,
        asserted_deferred_collision_count=asserted_deferred_collision_count,
        contract_reason_codes=contract_reason_codes,
        passed=status == "pass",
        observations=observation_scores,
    )


def evaluate_extraction_dataset(
    dataset: ExtractionSeedDataset,
    actual_by_case_id: dict[str, GroundedVisualExtractionResult],
    *,
    candidates_by_case_id: dict[str, VisualCandidateExtractionResult] | None = None,
    packets_by_case_id: dict[str, GroundedCandidatePacket] | None = None,
) -> ExtractionDatasetScore:
    missing = sorted({case.id for case in dataset.cases} - set(actual_by_case_id))
    if missing:
        raise ValueError(f"missing_seed_case_outputs:{','.join(missing)}")
    case_scores = [
        evaluate_extraction_case(
            case,
            actual_by_case_id[case.id],
            candidates=(
                candidates_by_case_id.get(case.id)
                if candidates_by_case_id is not None
                else None
            ),
            packet=(
                packets_by_case_id.get(case.id)
                if packets_by_case_id is not None
                else None
            ),
        )
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
    expected_count = sum(
        len(case.effective_required_observations) for case in dataset.cases
    )
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
        allowed_observation_count=sum(
            item.allowed_observation_count for item in case_scores
        ),
        unlisted_observation_count=sum(
            item.unlisted_observation_count for item in case_scores
        ),
        forbidden_observation_count=sum(
            item.forbidden_observation_count for item in case_scores
        ),
        mention_failure_count=sum(item.mention_failure_count for item in case_scores),
        deferred_failure_count=sum(item.deferred_failure_count for item in case_scores),
        temporal_failure_count=sum(item.temporal_failure_count for item in case_scores),
        duplicate_temporal_signal_count=sum(
            item.duplicate_temporal_signal_count for item in case_scores
        ),
        asserted_deferred_collision_count=sum(
            item.asserted_deferred_collision_count for item in case_scores
        ),
        cases=case_scores,
    )
