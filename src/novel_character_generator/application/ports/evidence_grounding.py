from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from novel_character_generator.application.ports.visual_evidence import (
    VisualEvidenceDiscoveryResult,
)

EVIDENCE_GROUNDING_INPUT_SCHEMA_VERSION: Literal["evidence-grounding-input-v2"] = (
    "evidence-grounding-input-v2"
)
EVIDENCE_GROUNDING_OUTPUT_SCHEMA_VERSION: Literal["grounded-evidence-packet-v2"] = (
    "grounded-evidence-packet-v2"
)
EVIDENCE_GROUNDING_POLICY_VERSION: Literal["evidence-grounding-policy-v2"] = (
    "evidence-grounding-policy-v2"
)
EVIDENCE_CONTEXT_POLICY_VERSION: Literal["evidence-context-sentence-window-v2"] = (
    "evidence-context-sentence-window-v2"
)
EVIDENCE_GROUNDING_ARTIFACT_SCHEMA_VERSION: Literal[
    "deterministic-decision-artifact-v1"
] = "deterministic-decision-artifact-v1"

AcceptedEvidenceGroundingStatus = Literal["exact", "whitespace_unique"]
MentionGroundingStatus = Literal["exact", "whitespace_unique", "ambiguous", "not_found"]
EvidenceGroundingReasonCode = Literal[
    "quote_not_in_chunk",
    "ambiguous_evidence",
    "local_context_budget_exceeded",
    "deterministic_duplicate",
]


class EvidenceGroundingExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["evidence-grounding-input-v2"]
    run_id: str = Field(min_length=1, max_length=200)
    source_document_version_id: str = Field(min_length=1, max_length=200)
    chunk_id: str = Field(min_length=1, max_length=200)
    chunk_text: str = Field(min_length=1)
    discovery: VisualEvidenceDiscoveryResult
    max_context_chars: int = Field(default=600, ge=64, le=4_000)

    @model_validator(mode="after")
    def validate_chunk_identity(self) -> EvidenceGroundingExecutionRequest:
        if self.discovery.chunk_id != self.chunk_id:
            raise ValueError("evidence_grounding_chunk_id_mismatch")
        return self


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    source_quote: str = Field(min_length=1)
    quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_bounds(self) -> EvidenceSpan:
        if self.end <= self.start:
            raise ValueError("invalid_evidence_span")
        return self


class EvidenceContextWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["evidence-context-sentence-window-v2"]
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)
    focus_start: int = Field(ge=0)
    focus_end: int = Field(gt=0)
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_window(self) -> EvidenceContextWindow:
        if self.end <= self.start or self.focus_end <= self.focus_start:
            raise ValueError("invalid_evidence_context_window")
        if self.focus_end > len(self.text):
            raise ValueError("evidence_context_focus_out_of_range")
        return self


class EvidenceMentionNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    local_owner_id: str = Field(pattern=r"^m[1-9][0-9]*$")
    mention_quote: str = Field(min_length=1)
    grounding_status: MentionGroundingStatus
    occurrence_count: int = Field(ge=0)
    evidence_span: EvidenceSpan | None = None

    @model_validator(mode="after")
    def validate_status_span(self) -> EvidenceMentionNode:
        located = self.grounding_status in {"exact", "whitespace_unique"}
        if located != (self.evidence_span is not None):
            raise ValueError("mention_grounding_status_span_mismatch")
        return self


class GroundedEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(pattern=r"^ge_[0-9a-f]{32}$")
    source_candidate_id: str = Field(pattern=r"^c[1-9][0-9]*$")
    local_owner_id: str | None = Field(default=None, pattern=r"^m[1-9][0-9]*$")
    evidence_quote: str = Field(min_length=1)
    evidence_span: EvidenceSpan
    grounding_status: AcceptedEvidenceGroundingStatus
    local_context: EvidenceContextWindow


class EvidenceGroundingIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_candidate_id: str = Field(pattern=r"^c[1-9][0-9]*$")
    local_owner_id: str | None = Field(default=None, pattern=r"^m[1-9][0-9]*$")
    evidence_quote: str = Field(min_length=1)
    reason_code: EvidenceGroundingReasonCode
    occurrence_count: int = Field(default=0, ge=0)


class GroundedEvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["grounded-evidence-packet-v2"]
    run_id: str = Field(min_length=1, max_length=200)
    source_document_version_id: str = Field(min_length=1, max_length=200)
    chunk_id: str = Field(min_length=1, max_length=200)
    grounding_policy_version: Literal["evidence-grounding-policy-v2"]
    context_policy_version: Literal["evidence-context-sentence-window-v2"]
    mention_nodes: tuple[EvidenceMentionNode, ...]
    grounded_candidates: tuple[GroundedEvidenceItem, ...]
    rejected_items: tuple[EvidenceGroundingIssue, ...]
    deferred_items: tuple[EvidenceGroundingIssue, ...]

    @model_validator(mode="after")
    def validate_owner_graph(self) -> GroundedEvidencePacket:
        owner_ids = {item.local_owner_id for item in self.mention_nodes}
        candidate_owner_ids = {
            item.local_owner_id
            for item in self.grounded_candidates
            if item.local_owner_id is not None
        }
        dangling = candidate_owner_ids - owner_ids
        if dangling:
            raise ValueError(f"unknown_grounded_evidence_owner:{','.join(sorted(dangling))}")
        return self


class EvidenceGroundingArtifactCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mentions: int = Field(ge=0)
    grounded_candidates: int = Field(ge=0)
    rejected_items: int = Field(ge=0)
    deferred_items: int = Field(ge=0)


class EvidenceGroundingDecisionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["deterministic-decision-artifact-v1"]
    node_id: Literal["N2"]
    run_id: str
    source_document_version_id: str
    chunk_id: str
    grounding_policy_version: Literal["evidence-grounding-policy-v2"]
    context_policy_version: Literal["evidence-context-sentence-window-v2"]
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["succeeded", "completed_with_warnings"]
    reason_codes: tuple[str, ...]
    counts: EvidenceGroundingArtifactCounts
    output: GroundedEvidencePacket
