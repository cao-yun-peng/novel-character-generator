from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENTITY_RESOLUTION_SCHEMA_VERSION = "character-entity-resolution-v1"
ENTITY_CONVERGENCE_BATCH_SIZE = 10


class GroundedMentionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention_id: str = Field(min_length=1, max_length=256)
    local_entity_id: str = Field(min_length=1, max_length=64)
    representative_name: str = Field(min_length=1, max_length=100)
    mention_text: str = Field(min_length=1, max_length=200)
    mention_kind: Literal["name", "title", "kinship", "disguise", "nickname"]
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class GroundedFactCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention_id: str = Field(min_length=1, max_length=256)
    field_path: str = Field(min_length=1, max_length=200)
    value: object
    evidence_quote: str = Field(min_length=1, max_length=500)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    epistemic_status: Literal["asserted", "negated"]
    confidence: float = Field(ge=0, le=1)
    candidate_key: str | None = Field(default=None, max_length=256)
    life_phase_key: str | None = Field(default=None, max_length=100)
    life_phase_label: str | None = Field(default=None, max_length=100)


class GroundedTemporalSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(min_length=1, max_length=256)
    mention_id: str | None = Field(default=None, max_length=256)
    fact_candidate_key: str | None = Field(default=None, max_length=256)
    kind: Literal[
        "age", "life_phase", "time_jump", "presentation", "transformation", "other"
    ]
    label: str = Field(min_length=1, max_length=100)
    evidence_quote: str = Field(min_length=1, max_length=300)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class GroundedCandidatePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mentions: list[GroundedMentionCandidate] = Field(default_factory=list, max_length=128)
    facts: list[GroundedFactCandidate] = Field(default_factory=list, max_length=256)
    temporal_signals: list[GroundedTemporalSignal] = Field(default_factory=list, max_length=512)
    warnings: list[str] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def validate_fact_owners(self) -> GroundedCandidatePacket:
        mention_ids = [item.mention_id for item in self.mentions]
        if len(mention_ids) != len(set(mention_ids)):
            raise ValueError("duplicate_grounded_mention_id")
        dangling = {item.mention_id for item in self.facts} - set(mention_ids)
        if dangling:
            raise ValueError(f"unknown_grounded_fact_mention:{','.join(sorted(dangling))}")
        dangling_signals = {
            item.mention_id for item in self.temporal_signals if item.mention_id is not None
        } - set(mention_ids)
        if dangling_signals:
            raise ValueError(
                f"unknown_grounded_signal_mention:{','.join(sorted(dangling_signals))}"
            )
        signal_ids = [item.signal_id for item in self.temporal_signals]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("duplicate_grounded_temporal_signal_id")
        return self


class EntityMemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1, max_length=256)
    character_id: UUID | None = None
    canonical_name: str | None = Field(default=None, max_length=255)
    status: Literal["stable", "provisional", "unresolved"]
    mention_ids: list[str] = Field(default_factory=list, max_length=2_000)
    names: list[str] = Field(default_factory=list, max_length=64)
    explicit_names: list[str] = Field(
        default_factory=list,
        max_length=64,
        description=(
            "Names originating from mention_kind=name. They are kept separate from titles, "
            "kinship terms, disguises, and nicknames so deterministic identity gates can fail "
            "closed on cross-name merges."
        ),
    )
    evidence_quotes: list[str] = Field(default_factory=list, max_length=64)
    last_chunk_ordinal: int = Field(ge=0)


class EntityResolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    chunk_ordinal: int = Field(ge=0)
    chunk_text: str
    text_truncated: bool = False
    previous_chunk_tail: str = Field(default="", max_length=4_000)
    candidates: GroundedCandidatePacket
    cumulative_memory: list[EntityMemoryRecord] = Field(default_factory=list, max_length=2_000)
    historical_evidence: list[str] = Field(default_factory=list, max_length=256)


class EntityMentionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention_id: str = Field(min_length=1, max_length=256)
    action: Literal["link_existing", "create_candidate", "unresolved"]
    target_memory_id: str | None = Field(default=None, max_length=256)
    related_mention_ids: list[str] = Field(
        default_factory=list,
        max_length=128,
        description=(
            "Historical mention IDs copied only from cumulative_memory[*].mention_ids; never "
            "include the current mention_id, local entity IDs, names, or invented IDs."
        ),
    )
    evidence_quotes: list[str] = Field(
        default_factory=list,
        min_length=1,
        max_length=16,
        description=(
            "Shortest continuous verbatim substrings copied exactly from chunk_text, "
            "previous_chunk_tail, or historical_evidence."
        ),
    )
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_action_target(self) -> EntityMentionDecision:
        if self.action == "link_existing" and self.target_memory_id is None:
            raise ValueError("link_existing_requires_target_memory_id")
        if self.action != "link_existing" and self.target_memory_id is not None:
            raise ValueError("non_link_action_forbids_target_memory_id")
        return self


class EntityResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[EntityMentionDecision] = Field(default_factory=list, max_length=128)


class EntityConvergenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_index: int = Field(ge=0)
    start_chunk_ordinal: int = Field(ge=0)
    end_chunk_ordinal: int = Field(ge=0)
    final_batch: bool
    stable_memory: list[EntityMemoryRecord] = Field(default_factory=list, max_length=2_000)
    provisional_memory: list[EntityMemoryRecord] = Field(default_factory=list, max_length=2_000)
    chapter_decisions: list[dict[str, object]] = Field(default_factory=list, max_length=32)
    evidence_snippets: list[str] = Field(default_factory=list, max_length=512)


class EntityConvergenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention_ids: list[str] = Field(
        min_length=1,
        max_length=2_000,
        description="Mention IDs copied from the supplied stable or provisional memory records.",
    )
    action: Literal[
        "confirm_link",
        "create_character",
        "keep_unresolved",
        "split_candidate",
        "reject_candidate",
    ]
    target_character_id: UUID | None = Field(
        default=None,
        description=(
            "For confirm_link only: copy a non-null character_id UUID from stable_memory. Never "
            "use memory_id or candidate:* values."
        ),
    )
    canonical_name: str | None = Field(
        default=None,
        max_length=255,
        description="Required with create_character or split_candidate.",
    )
    creation_key: str | None = Field(
        default=None,
        max_length=256,
        description=(
            "Stable grouping key required with create_character or split_candidate; it is not a "
            "character UUID or memory_id."
        ),
    )
    evidence_quotes: list[str] = Field(
        default_factory=list,
        min_length=1,
        max_length=32,
        description=(
            "Shortest continuous verbatim substrings copied exactly from evidence_snippets."
        ),
    )
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_materialization_target(self) -> EntityConvergenceDecision:
        if self.action == "confirm_link" and self.target_character_id is None:
            raise ValueError("confirm_link_requires_target_character_id")
        if self.action in {"create_character", "split_candidate"} and (
            self.canonical_name is None or self.creation_key is None
        ):
            raise ValueError("character_creation_requires_name_and_key")
        if self.action != "confirm_link" and self.target_character_id is not None:
            raise ValueError("non_link_action_forbids_target_character_id")
        return self


class EntityConvergenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[EntityConvergenceDecision] = Field(default_factory=list, max_length=2_000)


class EntityResolutionProvider(Protocol):
    version: str

    async def resolve_chunk(self, request: EntityResolutionInput) -> EntityResolutionResult: ...

    async def converge_batch(self, request: EntityConvergenceInput) -> EntityConvergenceResult: ...
