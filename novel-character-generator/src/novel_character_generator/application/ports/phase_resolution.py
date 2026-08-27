from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PHASE_RESOLUTION_SCHEMA_VERSION = "character-phase-resolution-v1"
TemporalSignalKind = Literal[
    "age", "life_phase", "time_jump", "presentation", "transformation", "other"
]
PresentationMode = Literal[
    "direct", "flashback", "flashforward", "dream", "illusion", "rumor", "hypothetical"
]
RealityStatus = Literal["canonical", "subjective", "alleged", "counterfactual"]
ScopeType = Literal["instant", "scene", "chapter", "interval", "persistent", "unknown"]


class PhaseSignalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    kind: TemporalSignalKind
    label: str = Field(min_length=1, max_length=100)
    evidence_quote: str = Field(min_length=1, max_length=300)
    chapter_ordinal: int | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
    observation_ids: list[UUID] = Field(default_factory=list, max_length=512)


class PhaseObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    mention_span_id: UUID | None = None
    field_path: str = Field(min_length=1, max_length=255)
    chapter_ordinal: int | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
    current_scope: dict[str, object] = Field(default_factory=dict)


class CharacterPhaseResolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: UUID
    timeline_id: UUID
    signals: list[PhaseSignalInput] = Field(default_factory=list, max_length=10_000)
    observations: list[PhaseObservationInput] = Field(default_factory=list, max_length=10_000)


class CharacterLifePhaseDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    phase_order: int = Field(ge=0)
    age_stage: str | None = Field(default=None, max_length=100)
    start_chapter_ordinal: int | None = Field(default=None, ge=0)
    end_chapter_ordinal: int | None = Field(default=None, ge=0)
    evidence_signal_ids: list[UUID] = Field(min_length=1, max_length=10_000)
    confidence: float = Field(ge=0, le=1)
    status: Literal["candidate", "active"]


class ObservationScopeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: UUID
    phase_key: str | None = Field(default=None, max_length=100)
    presentation_mode: PresentationMode
    reality_status: RealityStatus
    transformation_state: str | None = Field(default=None, max_length=100)
    scope_type: ScopeType
    start_chapter_ordinal: int | None = Field(default=None, ge=0)
    end_chapter_ordinal: int | None = Field(default=None, ge=0)
    status: Literal["final", "needs_review"]
    confidence: float = Field(ge=0, le=1)
    evidence_signal_ids: list[UUID] = Field(default_factory=list, max_length=10_000)
    reason_codes: list[str] = Field(default_factory=list, max_length=32)


class CharacterPhaseResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phases: list[CharacterLifePhaseDraft] = Field(default_factory=list, max_length=2_000)
    scope_decisions: list[ObservationScopeDecision] = Field(default_factory=list, max_length=10_000)
