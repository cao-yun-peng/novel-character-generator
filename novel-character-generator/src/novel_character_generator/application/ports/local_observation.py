from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_character_generator.application.ports.extraction import ExtractionCallMetadata
from novel_character_generator.domain.policies.mention_kinds import MentionKind

LOCAL_OBSERVATION_INPUT_SCHEMA_VERSION: Literal[
    "local-observation-discovery-input-v1.1"
] = "local-observation-discovery-input-v1.1"
LOCAL_OBSERVATION_OUTPUT_SCHEMA_VERSION: Literal[
    "local-observation-discovery-v1.1"
] = "local-observation-discovery-v1.1"
LOCAL_OBSERVATION_CONTRACT_VERSION: Literal[
    "local-observation-contract-v1.1"
] = "local-observation-contract-v1.1"
LOCAL_OBSERVATION_ARTIFACT_SCHEMA_VERSION: Literal[
    "model-decision-artifact-v1"
] = "model-decision-artifact-v1"
LOCAL_OBSERVATION_PROMPT_VERSION: Literal[
    "local-observation-discovery-prompt-v1.1"
] = "local-observation-discovery-prompt-v1.1"

CoarseVisualFamily = Literal[
    "physical_identity",
    "hair",
    "face",
    "body",
    "clothing",
    "worn_accessory",
    "cleanliness",
    "injury",
    "distinctive_mark",
    "disguise",
    "other_visual",
]

EpistemicStatus = Literal["asserted", "negated", "uncertain", "inferred"]
TemporalSignalKind = Literal[
    "age",
    "life_phase",
    "time_jump",
    "presentation",
    "transformation",
    "other_state",
]
UnresolvedReasonCode = Literal[
    "ambiguous_owner",
    "ambiguous_evidence",
    "ambiguous_local_scope",
    "unsupported_visual_content",
]

DEFAULT_COARSE_VISUAL_FAMILIES: tuple[CoarseVisualFamily, ...] = (
    "physical_identity",
    "hair",
    "face",
    "body",
    "clothing",
    "worn_accessory",
    "cleanliness",
    "injury",
    "distinctive_mark",
    "disguise",
    "other_visual",
)


class LocalObservationDiscoveryInput(BaseModel):
    """The complete semantic payload sent to M1 for one frozen chunk."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["local-observation-discovery-input-v1.1"]
    chunk_id: str = Field(min_length=1, max_length=200)
    chunk_text: str = Field(min_length=1)
    previous_tail: str | None
    allowed_coarse_families: list[CoarseVisualFamily] = Field(min_length=1)

    @field_validator("chunk_id", "chunk_text")
    @classmethod
    def reject_blank_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank_local_observation_input")
        return value

    @field_validator("allowed_coarse_families")
    @classmethod
    def reject_duplicate_families(
        cls, value: list[CoarseVisualFamily]
    ) -> list[CoarseVisualFamily]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate_allowed_coarse_family")
        return value


class LocalObservationEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_entity_id: str = Field(pattern=r"^e[1-9][0-9]*$")
    mention_quote: str = Field(min_length=1)
    mention_kind: MentionKind
    representative_name: str = Field(min_length=1)


class LocalObservationFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_fact_id: str = Field(pattern=r"^f[1-9][0-9]*$")
    entity_ref: str = Field(pattern=r"^e[1-9][0-9]*$")
    evidence_quote: str = Field(min_length=1)
    raw_proposition: str = Field(min_length=1)
    coarse_family: CoarseVisualFamily
    epistemic_status: EpistemicStatus


class LocalObservationTemporalSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_signal_id: str = Field(pattern=r"^t[1-9][0-9]*$")
    entity_ref: str | None = Field(pattern=r"^e[1-9][0-9]*$")
    fact_ref: str | None = Field(pattern=r"^f[1-9][0-9]*$")
    evidence_quote: str = Field(min_length=1)
    signal_kind: TemporalSignalKind
    raw_label: str = Field(min_length=1)


class LocalObservationUnresolvedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_item_id: str = Field(pattern=r"^u[1-9][0-9]*$")
    entity_ref: str | None = Field(pattern=r"^e[1-9][0-9]*$")
    evidence_quote: str = Field(min_length=1)
    raw_proposition: str = Field(min_length=1)
    reason_code: UnresolvedReasonCode


class LocalObservationDiscoveryResult(BaseModel):
    """Untrusted M1 output before source-bound deterministic validation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["local-observation-discovery-v1.1"]
    chunk_id: str = Field(min_length=1, max_length=200)
    entities: list[LocalObservationEntity] = Field(max_length=128)
    facts: list[LocalObservationFact] = Field(max_length=256)
    temporal_signals: list[LocalObservationTemporalSignal] = Field(max_length=128)
    unresolved_items: list[LocalObservationUnresolvedItem] = Field(max_length=128)

    @model_validator(mode="after")
    def validate_local_graph(self) -> LocalObservationDiscoveryResult:
        entity_ids = [item.local_entity_id for item in self.entities]
        fact_ids = [item.local_fact_id for item in self.facts]
        signal_ids = [item.local_signal_id for item in self.temporal_signals]
        unresolved_ids = [item.local_item_id for item in self.unresolved_items]
        for label, identifiers in (
            ("entity", entity_ids),
            ("fact", fact_ids),
            ("signal", signal_ids),
            ("unresolved", unresolved_ids),
        ):
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"duplicate_local_{label}_id")

        known_entities = set(entity_ids)
        known_facts = {item.local_fact_id: item for item in self.facts}
        referenced_entities = {item.entity_ref for item in self.facts}
        referenced_entities.update(
            item.entity_ref for item in self.temporal_signals if item.entity_ref is not None
        )
        referenced_entities.update(
            item.entity_ref for item in self.unresolved_items if item.entity_ref is not None
        )
        dangling_entities = sorted(referenced_entities - known_entities)
        if dangling_entities:
            raise ValueError(f"unknown_local_entity_ref:{','.join(dangling_entities)}")

        dangling_facts = sorted(
            item.fact_ref
            for item in self.temporal_signals
            if item.fact_ref is not None and item.fact_ref not in known_facts
        )
        if dangling_facts:
            raise ValueError(f"unknown_local_fact_ref:{','.join(dangling_facts)}")
        for signal in self.temporal_signals:
            if signal.fact_ref is None or signal.entity_ref is None:
                continue
            if known_facts[signal.fact_ref].entity_ref != signal.entity_ref:
                raise ValueError("temporal_signal_owner_mismatch")
        return self


class DetailedLocalObservationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    output: LocalObservationDiscoveryResult
    metadata: ExtractionCallMetadata
    raw_response: Any | None = None
    raw_message_content: Any | None = None


class LocalObservationExecutionRequest(BaseModel):
    """Shadow execution envelope; it has no persistence authority."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=200)
    source_document_version_id: str = Field(min_length=1, max_length=200)
    data_policy_version: str = Field(min_length=1, max_length=200)
    evaluation_attempt_id: str | None = Field(default=None, min_length=1, max_length=200)
    payload: LocalObservationDiscoveryInput


class LocalObservationArtifactCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: int = Field(ge=0)
    facts: int = Field(ge=0)
    temporal_signals: int = Field(ge=0)
    unresolved_items: int = Field(ge=0)


class LocalObservationDecisionArtifact(BaseModel):
    """Immutable, side-effect-free result returned by the M1 shadow slice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["model-decision-artifact-v1"]
    node_id: Literal["M1"]
    run_id: str
    source_document_version_id: str
    chunk_id: str
    evaluation_attempt_id: str | None
    contract_version: Literal["local-observation-contract-v1.1"]
    prompt_version: Literal["local-observation-discovery-prompt-v1.1"]
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config_version: str = Field(min_length=1)
    data_policy_version: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["succeeded", "completed_with_warnings"]
    reason_codes: tuple[str, ...]
    counts: LocalObservationArtifactCounts
    usage: ExtractionCallMetadata
    output: LocalObservationDiscoveryResult


class LocalObservationProvider(Protocol):
    version: str
    model_config_version: str
    prompt_version: Literal["local-observation-discovery-prompt-v1.1"]
    prompt_hash: str

    async def discover_detailed(
        self, request: LocalObservationDiscoveryInput
    ) -> DetailedLocalObservationResult: ...
