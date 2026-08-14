from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Timeline(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    novel_id: UUID
    name: str = Field(min_length=1)
    parent_timeline_id: UUID | None = None
    branch_event_id: UUID | None = None
    canonicality: Literal["canonical", "alternate", "hypothetical"] = "canonical"


class StoryEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timeline_id: UUID
    name: str | None = None
    story_order: Decimal | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class EventParticipant(BaseModel):
    event_id: UUID
    character_id: UUID
    role: Literal["actor", "patient", "observer", "speaker", "other"]
    evidence_observation_ids: list[UUID] = Field(default_factory=list)


class Scene(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    novel_id: UUID
    timeline_id: UUID
    event_id: UUID | None = None
    chapter_ordinal: int = Field(ge=0)
    narrative_order: int = Field(ge=0)
    point_of_view_character_id: UUID | None = None
    label: str | None = None
    source_document_version_id: UUID | None = None
    source_chunk_id: UUID | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, gt=0)
    presentation_mode: Literal[
        "direct", "flashback", "flashforward", "dream", "illusion", "rumor", "hypothetical"
    ] = "direct"
    reality_status: Literal["canonical", "subjective", "alleged", "counterfactual"] = (
        "canonical"
    )
    confidence: float | None = Field(default=None, ge=0, le=1)
    binding_status: Literal["hypothesis", "confirmed", "corrected"] = "hypothesis"
    binding_revision: int = Field(default=1, ge=1)
    created_by_run_id: UUID | None = None
