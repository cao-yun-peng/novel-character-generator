from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from novel_character_generator.application.ports.local_observation import (
    CoarseVisualFamily,
    EpistemicStatus,
    LocalObservationDiscoveryResult,
    TemporalSignalKind,
)
from novel_character_generator.domain.policies.mention_kinds import MentionKind

LOCAL_GROUNDING_INPUT_SCHEMA_VERSION: Literal["local-grounding-input-v1"] = (
    "local-grounding-input-v1"
)
LOCAL_GROUNDING_OUTPUT_SCHEMA_VERSION: Literal["grounded-local-packet-v1"] = (
    "grounded-local-packet-v1"
)
LOCAL_GROUNDING_ARTIFACT_SCHEMA_VERSION: Literal["deterministic-decision-artifact-v1"] = (
    "deterministic-decision-artifact-v1"
)
LOCAL_GROUNDING_POLICY_VERSION: Literal["local-grounding-policy-v1"] = "local-grounding-policy-v1"
LOCAL_CONTEXT_POLICY_VERSION: Literal["local-context-sentence-window-v1"] = (
    "local-context-sentence-window-v1"
)

AcceptedGroundingStatus = Literal["exact", "normalized_unique"]
MentionGroundingStatus = Literal[
    "exact", "normalized_unique", "ambiguous", "not_found", "unsupported_repair"
]
GroundingIssueRoute = Literal["rejected", "deferred"]
GroundingSourceKind = Literal["fact", "temporal_signal", "unresolved_item"]
GroundingIssueReasonCode = Literal[
    "quote_not_in_chunk",
    "ambiguous_evidence",
    "unsupported_quote_repair",
    "deterministic_duplicate",
    "asserted_unresolved_double_write",
    "local_context_budget_exceeded",
    "grounded_fact_unavailable",
    "ambiguous_owner",
    "ambiguous_local_scope",
    "unsupported_visual_content",
]


class LocalGroundingExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["local-grounding-input-v1"]
    run_id: str = Field(min_length=1, max_length=200)
    source_document_version_id: str = Field(min_length=1, max_length=200)
    chunk_id: str = Field(min_length=1, max_length=200)
    chunk_text: str = Field(min_length=1)
    discovery: LocalObservationDiscoveryResult
    max_context_chars: int = Field(default=600, ge=64, le=4_000)

    @model_validator(mode="after")
    def validate_chunk_identity(self) -> LocalGroundingExecutionRequest:
        if self.discovery.chunk_id != self.chunk_id:
            raise ValueError("local_grounding_chunk_id_mismatch")
        return self


class GroundedEvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    source_quote: str = Field(min_length=1)
    quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_bounds(self) -> GroundedEvidenceSpan:
        if self.end <= self.start:
            raise ValueError("invalid_grounded_evidence_span")
        return self


class LocalContextWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["local-context-sentence-window-v1"]
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)
    focus_start: int = Field(ge=0)
    focus_end: int = Field(gt=0)
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_window(self) -> LocalContextWindow:
        if self.end <= self.start or self.focus_end <= self.focus_start:
            raise ValueError("invalid_local_context_window")
        if self.focus_end > len(self.text):
            raise ValueError("local_context_focus_out_of_range")
        return self


class GroundedMentionNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    local_entity_id: str = Field(pattern=r"^e[1-9][0-9]*$")
    mention_quote: str = Field(min_length=1)
    mention_kind: MentionKind
    representative_name: str = Field(min_length=1)
    grounding_status: MentionGroundingStatus
    occurrence_count: int = Field(ge=0)
    evidence_span: GroundedEvidenceSpan | None = None

    @model_validator(mode="after")
    def validate_status_span(self) -> GroundedMentionNode:
        located = self.grounding_status in {"exact", "normalized_unique"}
        if located != (self.evidence_span is not None):
            raise ValueError("mention_grounding_status_span_mismatch")
        return self


class GroundedLocalFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str = Field(pattern=r"^gf_[0-9a-f]{32}$")
    local_fact_id: str = Field(pattern=r"^f[1-9][0-9]*$")
    local_entity_id: str = Field(pattern=r"^e[1-9][0-9]*$")
    evidence_quote: str = Field(min_length=1)
    evidence_span: GroundedEvidenceSpan
    grounding_status: AcceptedGroundingStatus
    raw_proposition: str = Field(min_length=1)
    coarse_family: CoarseVisualFamily
    epistemic_status: EpistemicStatus
    local_context: LocalContextWindow


class GroundedLocalSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: str = Field(pattern=r"^gs_[0-9a-f]{32}$")
    local_signal_id: str = Field(pattern=r"^t[1-9][0-9]*$")
    local_entity_id: str | None = Field(pattern=r"^e[1-9][0-9]*$")
    grounded_fact_id: str | None = Field(pattern=r"^gf_[0-9a-f]{32}$")
    evidence_quote: str = Field(min_length=1)
    evidence_span: GroundedEvidenceSpan
    grounding_status: AcceptedGroundingStatus
    signal_kind: TemporalSignalKind


class LocalGroundingIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route: GroundingIssueRoute
    source_kind: GroundingSourceKind
    source_local_id: str = Field(min_length=1, max_length=64)
    local_entity_id: str | None = Field(default=None, max_length=64)
    evidence_quote: str = Field(min_length=1)
    reason_code: GroundingIssueReasonCode
    upstream_reason_code: str | None = Field(default=None, max_length=100)
    occurrence_count: int = Field(default=0, ge=0)


class GroundedLocalPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["grounded-local-packet-v1"]
    run_id: str = Field(min_length=1, max_length=200)
    source_document_version_id: str = Field(min_length=1, max_length=200)
    chunk_id: str = Field(min_length=1, max_length=200)
    grounding_policy_version: Literal["local-grounding-policy-v1"]
    context_policy_version: Literal["local-context-sentence-window-v1"]
    mention_nodes: tuple[GroundedMentionNode, ...]
    grounded_facts: tuple[GroundedLocalFact, ...]
    grounded_signals: tuple[GroundedLocalSignal, ...]
    rejected_items: tuple[LocalGroundingIssue, ...]
    deferred_items: tuple[LocalGroundingIssue, ...]

    @model_validator(mode="after")
    def validate_grounded_graph(self) -> GroundedLocalPacket:
        entity_ids = {item.local_entity_id for item in self.mention_nodes}
        fact_ids = {item.fact_id for item in self.grounded_facts}
        dangling_fact_owners = {item.local_entity_id for item in self.grounded_facts} - entity_ids
        if dangling_fact_owners:
            raise ValueError(
                f"unknown_grounded_fact_owner:{','.join(sorted(dangling_fact_owners))}"
            )
        dangling_signal_facts = {
            item.grounded_fact_id
            for item in self.grounded_signals
            if item.grounded_fact_id is not None
        } - fact_ids
        if dangling_signal_facts:
            raise ValueError(
                f"unknown_grounded_signal_fact:{','.join(sorted(dangling_signal_facts))}"
            )
        return self


class LocalGroundingArtifactCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mentions: int = Field(ge=0)
    grounded_facts: int = Field(ge=0)
    grounded_signals: int = Field(ge=0)
    rejected_items: int = Field(ge=0)
    deferred_items: int = Field(ge=0)


class LocalGroundingDecisionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["deterministic-decision-artifact-v1"]
    node_id: Literal["N2"]
    run_id: str
    source_document_version_id: str
    chunk_id: str
    grounding_policy_version: Literal["local-grounding-policy-v1"]
    context_policy_version: Literal["local-context-sentence-window-v1"]
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["succeeded", "completed_with_warnings"]
    reason_codes: tuple[str, ...]
    counts: LocalGroundingArtifactCounts
    output: GroundedLocalPacket
