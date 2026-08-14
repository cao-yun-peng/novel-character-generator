from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class MentionSpan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_document_version_id: UUID
    source_chunk_id: UUID
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    mention_text: str = Field(min_length=1)
    mention_kind: Literal["name", "title", "kinship", "disguise", "nickname", "pronoun"]
    candidate_character_ids: list[UUID] = Field(default_factory=list)
    resolved_character_id: UUID | None = None
    grounding_status: Literal["exact", "fuzzy", "ungrounded", "manually_grounded"]
    normalization_map_version: str

    @model_validator(mode="after")
    def validate_span(self) -> "MentionSpan":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class AliasAssertion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    alias_text: str = Field(min_length=1)
    normalized_alias: str = Field(min_length=1)
    mention_span_id: UUID
    proposed_character_id: UUID | None = None
    speaker_id: UUID | None = None
    scene_id: UUID | None = None
    timeline_id: UUID | None = None
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    opposing_evidence_ids: list[UUID] = Field(default_factory=list)
    status: Literal["proposed", "approved", "rejected", "superseded"] = "proposed"
