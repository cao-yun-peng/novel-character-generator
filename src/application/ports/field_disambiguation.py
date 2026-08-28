from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_character_generator.application.ports.local_grounding import GroundedLocalPacket
from novel_character_generator.application.ports.model_provider import ModelCallMetadata
from novel_character_generator.domain.policies.visual_field_catalog import (
    VISUAL_FIELD_CATALOG_VERSION,
)

FIELD_DISAMBIGUATION_INPUT_SCHEMA_VERSION: Literal["field-disambiguation-input-v1"] = (
    "field-disambiguation-input-v1"
)
FIELD_DISAMBIGUATION_OUTPUT_SCHEMA_VERSION: Literal["field-disambiguation-result-v1"] = (
    "field-disambiguation-result-v1"
)
FIELD_DISAMBIGUATION_CONTRACT_VERSION: Literal["field-disambiguation-contract-v1"] = (
    "field-disambiguation-contract-v1"
)
FIELD_DISAMBIGUATION_MODEL_WIRE_SCHEMA_VERSION: Literal[
    "field-disambiguation-model-wire-v1"
] = "field-disambiguation-model-wire-v1"
FIELD_DISAMBIGUATION_ARTIFACT_SCHEMA_VERSION: Literal["model-decision-artifact-v1"] = (
    "model-decision-artifact-v1"
)
FIELD_DISAMBIGUATION_PROMPT_VERSION: Literal["field-disambiguation-prompt-v1"] = (
    "field-disambiguation-prompt-v1"
)

FieldDecision = Literal["map", "defer", "reject"]
ReferentKind = Literal[
    "whole_character",
    "body_part",
    "garment",
    "accessory",
    "appearance_state",
    "other_visual",
]
FieldDecisionReasonCode = Literal[
    "explicit_atomic_mapping",
    "ambiguous_semantic_decomposition",
    "missing_semantic_context",
    "unsupported_visual_fact",
    "held_or_nearby_object",
    "non_visual_content",
]


class FieldDisambiguationExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["field-disambiguation-input-v1"]
    data_policy_version: str = Field(min_length=1, max_length=200)
    evaluation_attempt_id: str | None = Field(default=None, min_length=1, max_length=200)
    grounded_packet: GroundedLocalPacket


class FieldCatalogWireEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_path: str = Field(min_length=1)
    value_type: Literal["string"]
    description: str = Field(min_length=1)


class FieldDisambiguationModelFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_quote: str = Field(min_length=1)
    raw_proposition: str = Field(min_length=1)
    coarse_family: str = Field(min_length=1)
    epistemic_status: Literal["asserted", "negated", "uncertain", "inferred"]
    local_context: str = Field(min_length=1)


class FieldDisambiguationModelMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_unit_index: int = Field(ge=0, le=255)
    referent_kind: ReferentKind
    referent_quote: str | None = Field(default=None, min_length=1)
    field_path: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1)

    @field_validator("field_path", "normalized_value")
    @classmethod
    def reject_blank_mapping_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank_field_disambiguation_mapping_text")
        return value

    @model_validator(mode="after")
    def validate_null_referent(self) -> FieldDisambiguationModelMapping:
        if self.referent_quote is None and self.referent_kind != "whole_character":
            raise ValueError("null_referent_requires_whole_character")
        return self


class FieldDisambiguationModelDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_index: int = Field(ge=0, le=255)
    decision: FieldDecision
    mappings: list[FieldDisambiguationModelMapping] = Field(max_length=64)
    reason_code: FieldDecisionReasonCode

    @model_validator(mode="after")
    def validate_decision_shape(self) -> FieldDisambiguationModelDecision:
        if self.decision == "map":
            if not self.mappings:
                raise ValueError("mapped_fact_requires_mapping")
            if self.reason_code != "explicit_atomic_mapping":
                raise ValueError("mapped_fact_requires_explicit_reason")
        elif self.mappings:
            raise ValueError("non_mapped_fact_must_not_have_mappings")
        elif self.reason_code == "explicit_atomic_mapping":
            raise ValueError("non_mapped_fact_invalid_reason")
        if self.decision == "defer" and self.reason_code not in {
            "ambiguous_semantic_decomposition",
            "missing_semantic_context",
        }:
            raise ValueError("deferred_fact_invalid_reason")
        if self.decision == "reject" and self.reason_code not in {
            "unsupported_visual_fact",
            "held_or_nearby_object",
            "non_visual_content",
        }:
            raise ValueError("rejected_fact_invalid_reason")
        return self


class FieldDisambiguationModelOutput(BaseModel):
    """Minimal untrusted M2 wire output; all stable identifiers are absent."""

    model_config = ConfigDict(extra="forbid")

    decisions: list[FieldDisambiguationModelDecision] = Field(min_length=1, max_length=256)


class MappedFieldCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mapping_id: str = Field(pattern=r"^m[1-9][0-9]*$")
    semantic_unit_id: str = Field(pattern=r"^s[1-9][0-9]*$")
    referent_kind: ReferentKind
    referent_quote: str | None = Field(default=None, min_length=1)
    field_path: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1)
    evidence_quote: str = Field(min_length=1)


class FieldDisambiguationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str = Field(pattern=r"^gf_[0-9a-f]{32}$")
    evidence_quote: str = Field(min_length=1)
    decision: FieldDecision
    mappings: tuple[MappedFieldCandidate, ...]
    reason_code: FieldDecisionReasonCode

    @model_validator(mode="after")
    def validate_materialized_shape(self) -> FieldDisambiguationDecision:
        if self.decision == "map":
            if not self.mappings:
                raise ValueError("mapped_fact_requires_mapping")
            if self.reason_code != "explicit_atomic_mapping":
                raise ValueError("mapped_fact_requires_explicit_reason")
        elif self.mappings:
            raise ValueError("non_mapped_fact_must_not_have_mappings")
        elif self.reason_code == "explicit_atomic_mapping":
            raise ValueError("non_mapped_fact_invalid_reason")
        if self.decision == "defer" and self.reason_code not in {
            "ambiguous_semantic_decomposition",
            "missing_semantic_context",
        }:
            raise ValueError("deferred_fact_invalid_reason")
        if self.decision == "reject" and self.reason_code not in {
            "unsupported_visual_fact",
            "held_or_nearby_object",
            "non_visual_content",
        }:
            raise ValueError("rejected_fact_invalid_reason")
        return self


class FieldDisambiguationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["field-disambiguation-result-v1"]
    field_registry_version: Literal["visual-field-catalog-v1"]
    chunk_id: str = Field(min_length=1, max_length=200)
    decisions: tuple[FieldDisambiguationDecision, ...]


class DetailedFieldDisambiguationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    output: FieldDisambiguationResult
    metadata: ModelCallMetadata
    raw_response: Any | None = None
    raw_message_content: Any | None = None


class FieldDisambiguationArtifactCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_facts: int = Field(ge=0)
    mapped_facts: int = Field(ge=0)
    deferred_facts: int = Field(ge=0)
    rejected_facts: int = Field(ge=0)
    mappings: int = Field(ge=0)


class FieldDisambiguationDecisionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["model-decision-artifact-v1"]
    node_id: Literal["M2"]
    run_id: str
    source_document_version_id: str
    chunk_id: str
    evaluation_attempt_id: str | None
    contract_version: Literal["field-disambiguation-contract-v1"]
    field_registry_version: Literal["visual-field-catalog-v1"]
    prompt_version: Literal["field-disambiguation-prompt-v1"]
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config_version: str = Field(min_length=1)
    data_policy_version: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["succeeded", "completed_with_warnings"]
    reason_codes: tuple[str, ...]
    counts: FieldDisambiguationArtifactCounts
    usage: ModelCallMetadata
    output: FieldDisambiguationResult


class FieldDisambiguationProvider(Protocol):
    version: str
    model_config_version: str
    prompt_version: Literal["field-disambiguation-prompt-v1"]
    prompt_hash: str

    async def disambiguate_detailed(
        self, packet: GroundedLocalPacket
    ) -> DetailedFieldDisambiguationResult: ...


assert VISUAL_FIELD_CATALOG_VERSION == "visual-field-catalog-v1"
