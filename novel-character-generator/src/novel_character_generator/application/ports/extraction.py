from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class MentionDraft(BaseModel):
    text: str
    canonical_name: str | None
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    kind: Literal["name", "title", "kinship", "disguise", "nickname", "pronoun"]


class AliasDraft(BaseModel):
    alias_text: str
    canonical_name: str | None
    mention_start: int = Field(ge=0)
    mention_end: int = Field(gt=0)
    alias_kind: Literal["title", "kinship", "disguise", "nickname"]


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


class ExpressionDraft(BaseModel):
    character_name: str
    outward_emotion: Literal[
        "joy", "sadness", "anger", "fear", "surprise", "disgust", "calm", "mixed", "unknown"
    ]
    expression_text: str
    visible_cues: list[str] = Field(default_factory=list)
    internal_emotion: str | None = None
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class SceneHypothesisDraft(BaseModel):
    label: str | None = None
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    timeline_name: str | None = None
    presentation_mode: Literal[
        "direct", "flashback", "flashforward", "dream", "illusion", "rumor", "hypothetical"
    ] = "direct"
    reality_status: Literal["canonical", "subjective", "alleged", "counterfactual"] = (
        "canonical"
    )
    confidence: float = Field(ge=0, le=1)


class TimelineHypothesisDraft(BaseModel):
    name: str
    canonicality: Literal["canonical", "alternate", "hypothetical"]
    evidence_quote: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class RelationDraft(BaseModel):
    source_character_name: str
    target_character_name: str
    relation_type: str
    evidence_quote: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class ReferenceDraft(BaseModel):
    text: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    candidate_character_names: list[str] = Field(default_factory=list)


class ChunkExtractionResult(BaseModel):
    mentions: list[MentionDraft] = Field(default_factory=list)
    alias_hypotheses: list[AliasDraft] = Field(default_factory=list)
    observations: list[ObservationDraft] = Field(default_factory=list)
    expression_observations: list[ExpressionDraft] = Field(default_factory=list)
    scene_hypotheses: list[SceneHypothesisDraft] = Field(default_factory=list)
    timeline_hypotheses: list[TimelineHypothesisDraft] = Field(default_factory=list)
    relations: list[RelationDraft] = Field(default_factory=list)
    unresolved_references: list[ReferenceDraft] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExtractionProvider(Protocol):
    version: str

    async def extract_chunk(self, text: str) -> ChunkExtractionResult: ...
