from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EPISTEMIC_STATUS_ALIASES = {
    "asserted": "asserted",
    "stated": "asserted",
    "explicit": "asserted",
    "explicitly_stated": "asserted",
    "confirmed": "asserted",
    "fact": "asserted",
    "direct": "asserted",
    "明确": "asserted",
    "原文明示": "asserted",
    "negated": "negated",
    "denied": "negated",
    "absent": "negated",
    "否定": "negated",
    "inferred": "inferred",
    "implied": "inferred",
    "deduced": "inferred",
    "推断": "inferred",
    "uncertain": "uncertain",
    "possible": "uncertain",
    "ambiguous": "uncertain",
    "unknown": "uncertain",
    "不确定": "uncertain",
}


class VisualEntityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    representative_name: str = Field(min_length=1, max_length=100)
    mention_quote: str = Field(min_length=1, max_length=200)
    mention_kind: Literal["name", "title", "kinship", "disguise", "nickname"]
    confidence: float = Field(ge=0, le=1)


class VisualTemporalSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "age",
        "life_phase",
        "time_jump",
        "presentation",
        "transformation",
        "other",
    ]
    label: str = Field(min_length=1, max_length=100)
    evidence_quote: str = Field(min_length=1, max_length=300)


class VisualTemporalSignalCandidate(VisualTemporalSignal):
    """A chunk-level temporal signal that may exist without a visual fact."""

    entity_ref: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    confidence: float = Field(default=1.0, ge=0, le=1)


class VisualFactCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_ref: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    field_path: str = Field(min_length=1, max_length=200)
    value: Any
    evidence_quote: str = Field(min_length=1, max_length=500)
    epistemic_status: Literal["asserted", "negated", "inferred", "uncertain"] = "asserted"
    confidence: float = Field(ge=0, le=1)
    temporal_signals: list[VisualTemporalSignal] = Field(default_factory=list, max_length=8)

    @field_validator("epistemic_status", mode="before")
    @classmethod
    def normalize_epistemic_status(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        token = value.strip().casefold().replace("-", "_").replace(" ", "_")
        return EPISTEMIC_STATUS_ALIASES.get(token, value)


class VisualDeferredCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: Literal[
        "ambiguous_entity",
        "ambiguous_evidence",
        "uncertain_scope",
        "unsupported_visual_field",
    ]
    evidence_quote: str | None = Field(default=None, max_length=500)
    detail: str | None = Field(default=None, max_length=500)


class VisualCandidateExtractionResult(BaseModel):
    """The only remote extraction schema from visual-observation-v3 onward.

    The model discovers local entities and visual evidence candidates. It does not
    calculate offsets or decide novel-level entity identity, scenes, timelines,
    relations, or expressions.
    """

    model_config = ConfigDict(extra="forbid")

    entities: list[VisualEntityCandidate] = Field(default_factory=list, max_length=128)
    visual_candidates: list[VisualFactCandidate] = Field(default_factory=list, max_length=256)
    temporal_signals: list[VisualTemporalSignalCandidate] = Field(
        default_factory=list, max_length=128
    )
    deferred_items: list[VisualDeferredCandidate] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def validate_local_references(self) -> "VisualCandidateExtractionResult":
        local_ids = [entity.local_id for entity in self.entities]
        if len(local_ids) != len(set(local_ids)):
            raise ValueError("duplicate_visual_entity_local_id")
        known = set(local_ids)
        referenced_entities = {candidate.entity_ref for candidate in self.visual_candidates} | {
            signal.entity_ref for signal in self.temporal_signals if signal.entity_ref is not None
        }
        dangling = sorted(referenced_entities - known)
        if dangling:
            raise ValueError(f"unknown_visual_entity_ref:{','.join(dangling)}")
        return self


class MentionDraft(BaseModel):
    text: str
    canonical_name: str | None
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    kind: Literal["name", "title", "kinship", "disguise", "nickname", "pronoun"]


class ObservationDraft(BaseModel):
    character_name: str
    field_path: str
    value: Any
    evidence_quote: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    epistemic_status: Literal["asserted", "negated", "inferred", "uncertain"] = "asserted"
    confidence: float = Field(ge=0, le=1)
    life_phase_key: str | None = Field(default=None, max_length=100)
    life_phase_label: str | None = Field(default=None, max_length=100)

    @field_validator("epistemic_status", mode="before")
    @classmethod
    def normalize_epistemic_status(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        token = value.strip().casefold().replace("-", "_").replace(" ", "_")
        return EPISTEMIC_STATUS_ALIASES.get(token, value)


class GroundedVisualExtractionResult(BaseModel):
    """Server-grounded visual facts ready for the current persistence layer."""

    mentions: list[MentionDraft] = Field(default_factory=list)
    observations: list[ObservationDraft] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExtractionTokenUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    cache_hit_tokens: int = Field(default=0, ge=0)
    cache_miss_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ExtractionCallMetadata(BaseModel):
    wire_api: Literal["chat_completions", "responses"]
    provider_request_id: str | None = None
    response_model: str | None = None
    status: str
    finish_reason: str | None = None
    attempts: int = Field(default=1, ge=1)
    latency_ms: float = Field(ge=0)
    usage: ExtractionTokenUsage = Field(default_factory=ExtractionTokenUsage)


class DetailedExtractionResult(BaseModel):
    output: VisualCandidateExtractionResult
    metadata: ExtractionCallMetadata
    raw_response: Any | None = None
    raw_message_content: Any | None = None


class ExtractionProvider(Protocol):
    version: str

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult: ...


@runtime_checkable
class DetailedExtractionProvider(Protocol):
    async def extract_chunk_detailed(self, text: str) -> DetailedExtractionResult: ...
