from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from novel_character_generator.application.ports.model_provider import ModelCallMetadata

VISUAL_EVIDENCE_INPUT_SCHEMA_VERSION: Literal["visual-evidence-discovery-input-v2"] = (
    "visual-evidence-discovery-input-v2"
)
VISUAL_EVIDENCE_OUTPUT_SCHEMA_VERSION: Literal["visual-evidence-discovery-v2"] = (
    "visual-evidence-discovery-v2"
)
VISUAL_EVIDENCE_CONTRACT_VERSION: Literal["visual-evidence-contract-v2"] = (
    "visual-evidence-contract-v2"
)
VISUAL_EVIDENCE_MODEL_WIRE_SCHEMA_VERSION: Literal["visual-evidence-discovery-model-wire-v2"] = (
    "visual-evidence-discovery-model-wire-v2"
)
VISUAL_EVIDENCE_ARTIFACT_SCHEMA_VERSION: Literal["model-decision-artifact-v1"] = (
    "model-decision-artifact-v1"
)
VISUAL_EVIDENCE_SOURCE_MATCH_POLICY_VERSION: Literal[
    "visual-evidence-source-match-policy-v2"
] = "visual-evidence-source-match-policy-v2"
VisualEvidencePromptVersion = Literal["visual-evidence-discovery-prompt-v2.8"]
VISUAL_EVIDENCE_PROMPT_VERSION: VisualEvidencePromptVersion = (
    "visual-evidence-discovery-prompt-v2.8"
)


class VisualEvidenceDiscoveryInput(BaseModel):
    """Internal source envelope; the provider sends only chunk_text to M1 v2."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["visual-evidence-discovery-input-v2"]
    chunk_id: str = Field(min_length=1, max_length=200)
    chunk_text: str = Field(min_length=1)
    previous_tail: str | None = None

    @model_validator(mode="after")
    def reject_blank_text(self) -> VisualEvidenceDiscoveryInput:
        if not self.chunk_text.strip():
            raise ValueError("blank_visual_evidence_input")
        return self


class VisualEvidenceModelMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention_quote: str = Field(min_length=1)


class VisualEvidenceModelCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_index: int | None = Field(default=None, ge=0)
    evidence_quote: str = Field(min_length=1)


class VisualEvidenceModelOutput(BaseModel):
    """Untrusted M1 v2 wire response: verbatim evidence only."""

    model_config = ConfigDict(extra="forbid")

    mentions: list[VisualEvidenceModelMention] = Field(max_length=128)
    evidence_candidates: list[VisualEvidenceModelCandidate] = Field(max_length=256)

    @model_validator(mode="after")
    def validate_owner_indices(self) -> VisualEvidenceModelOutput:
        mention_count = len(self.mentions)
        if any(
            item.owner_index is not None and item.owner_index >= mention_count
            for item in self.evidence_candidates
        ):
            raise ValueError("visual_evidence_owner_index_out_of_range")
        return self


class VisualEvidenceMention(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mention_id: str = Field(pattern=r"^m[1-9][0-9]*$")
    mention_quote: str = Field(min_length=1)


class GroundedEvidenceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(pattern=r"^c[1-9][0-9]*$")
    local_owner_id: str | None = Field(default=None, pattern=r"^m[1-9][0-9]*$")
    evidence_quote: str = Field(min_length=1)


class VisualEvidenceDiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["visual-evidence-discovery-v2"]
    chunk_id: str = Field(min_length=1, max_length=200)
    mentions: tuple[VisualEvidenceMention, ...]
    evidence_candidates: tuple[GroundedEvidenceCandidate, ...]

    @model_validator(mode="after")
    def validate_candidate_owners(self) -> VisualEvidenceDiscoveryResult:
        mention_ids = {item.mention_id for item in self.mentions}
        dangling = {
            item.local_owner_id
            for item in self.evidence_candidates
            if item.local_owner_id is not None
        } - mention_ids
        if dangling:
            raise ValueError(f"unknown_visual_evidence_owner:{','.join(sorted(dangling))}")
        return self


class DetailedVisualEvidenceResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    output: VisualEvidenceDiscoveryResult
    metadata: ModelCallMetadata
    raw_response: Any | None = None
    raw_message_content: Any | None = None


class VisualEvidenceExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=200)
    source_document_version_id: str = Field(min_length=1, max_length=200)
    data_policy_version: str = Field(min_length=1, max_length=200)
    evaluation_attempt_id: str | None = Field(default=None, min_length=1, max_length=200)
    payload: VisualEvidenceDiscoveryInput


class VisualEvidenceArtifactCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mentions: int = Field(ge=0)
    evidence_candidates: int = Field(ge=0)


class VisualEvidenceDecisionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["model-decision-artifact-v1"]
    node_id: Literal["M1"]
    run_id: str
    source_document_version_id: str
    chunk_id: str
    evaluation_attempt_id: str | None
    contract_version: Literal["visual-evidence-contract-v2"]
    prompt_version: VisualEvidencePromptVersion
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config_version: str = Field(min_length=1)
    data_policy_version: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["succeeded", "completed_with_warnings"]
    reason_codes: tuple[str, ...]
    counts: VisualEvidenceArtifactCounts
    usage: ModelCallMetadata
    output: VisualEvidenceDiscoveryResult


class VisualEvidenceProvider(Protocol):
    version: str
    model_config_version: str
    prompt_version: VisualEvidencePromptVersion
    prompt_hash: str

    async def discover_detailed(
        self, request: VisualEvidenceDiscoveryInput
    ) -> DetailedVisualEvidenceResult: ...
