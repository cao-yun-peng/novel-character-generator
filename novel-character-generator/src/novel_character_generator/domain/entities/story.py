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


class Scene(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    novel_id: UUID
    timeline_id: UUID
    event_id: UUID | None = None
    chapter_ordinal: int = Field(ge=0)
    narrative_order: int = Field(ge=0)
    point_of_view_character_id: UUID | None = None
