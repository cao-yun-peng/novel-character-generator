from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from novel_character_generator.domain.value_objects.temporal import TemporalScope


class FeatureObservation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    character_id: UUID
    field_path: str = Field(min_length=1)
    value: Any
    source_kind: Literal["text", "manual"]
    source_document_version_id: UUID | None = None
    source_chunk_id: UUID | None = None
    mention_span_id: UUID | None = None
    evidence_quote: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    chapter_ordinal: int | None = Field(default=None, ge=0)
    scene_id: UUID | None = None
    event_id: UUID | None = None
    temporal_scope: TemporalScope | None = None
    epistemic_status: Literal["asserted", "negated", "inferred", "uncertain"]
    grounding_status: Literal["exact", "fuzzy", "ungrounded", "manually_grounded"]
    confidence: float = Field(ge=0, le=1)
    extraction_run_id: UUID | None = None
    manual_approval_id: UUID | None = None
    extractor_version: str
    supersedes_id: UUID | None = None
    record_status: Literal["active", "invalidated", "superseded"] = "active"
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    invalidated_at: datetime | None = None
    invalidated_by_run_id: UUID | None = None

    @model_validator(mode="after")
    def validate_text_source(self) -> "FeatureObservation":
        if self.source_kind == "text" and self.temporal_scope is None:
            raise ValueError("text observations require temporal_scope")
        if self.source_kind == "text":
            required = (
                self.source_document_version_id,
                self.source_chunk_id,
                self.evidence_quote,
                self.char_start,
                self.char_end,
                self.extraction_run_id,
            )
            if any(item is None for item in required):
                raise ValueError("text observations require immutable evidence provenance")
        if self.source_kind == "manual" and self.manual_approval_id is None:
            raise ValueError("manual observations require manual_approval_id")
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be provided together")
        if self.char_start is not None and self.char_end is not None:
            if self.char_end <= self.char_start:
                raise ValueError("char_end must be greater than char_start")
        return self


class FeatureSuggestion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    character_id: UUID
    field_path: str = Field(min_length=1)
    value: Any
    suggestion_kind: Literal["identity_prototype", "style_default"]
    resource_version: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    allowed_fields: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    status: Literal["candidate", "accepted", "rejected"] = "candidate"
    approval_id: UUID | None = None


class ExpressionObservation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    character_id: UUID
    source_document_version_id: UUID
    source_chunk_id: UUID
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    outward_emotion: Literal[
        "joy", "sadness", "anger", "fear", "surprise", "disgust", "calm", "mixed", "unknown"
    ]
    expression_text: str | None = None
    visible_cues: list[str] = Field(default_factory=list)
    intensity: float | None = Field(default=None, ge=0, le=1)
    valence: float | None = Field(default=None, ge=-1, le=1)
    arousal: float | None = Field(default=None, ge=0, le=1)
    is_masked: bool | None = None
    internal_emotion: str | None = None
    target_character_id: UUID | None = None
    cause_event_id: UUID | None = None
    scene_id: UUID | None = None
    temporal_scope: TemporalScope
    evidence_quote: str = Field(min_length=1)
    epistemic_status: Literal["asserted", "inferred", "uncertain"]
    confidence: float = Field(ge=0, le=1)
    extraction_run_id: UUID
    extractor_version: str

    @model_validator(mode="after")
    def validate_span(self) -> "ExpressionObservation":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class CharacterAppearanceState(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    character_id: UUID
    temporal_scope: TemporalScope
    label: str | None = None
    state_kind: Literal[
        "base_age_stage",
        "persistent_change",
        "disguise",
        "clothing",
        "temporary_condition",
        "manual_override",
    ] = "base_age_stage"
    merge_priority: int = 0
    age_stage: str | None = None
    face: dict[str, Any] | None = None
    body: dict[str, Any] | None = None
    hair: dict[str, Any] | None = None
    clothing: dict[str, Any] | None = None
    injuries: list[dict[str, Any]] = Field(default_factory=list)
    distinctive_marks: list[dict[str, Any]] = Field(default_factory=list)
    cleanliness: str | None = None
    disguise: str | None = None
    field_sources: dict[str, list[UUID]] = Field(default_factory=dict)
    resolver_version: str = "appearance-resolver-v1"
    created_by_run_id: UUID | None = None
    record_status: Literal["active", "invalidated", "superseded"] = "active"
    status: Literal["draft", "needs_review", "approved"] = "draft"


class CharacterRenderProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    character_id: UUID
    version: int = Field(default=1, ge=1)
    status: Literal["draft", "needs_review", "approved", "locked"] = "draft"
    identity_anchor: dict[str, Any] = Field(default_factory=dict)
    default_appearance_state_id: UUID | None = None
    default_stage_key: str | None = None
    appearance_state_ids: list[UUID] = Field(default_factory=list)
    palette: dict[str, Any] = Field(default_factory=dict)
    field_sources: dict[str, list[UUID]] = Field(default_factory=dict)
    field_suggestions: dict[str, Any] = Field(default_factory=dict)
    unresolved_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    style_preset: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    revision: int = Field(default=1, ge=1)
