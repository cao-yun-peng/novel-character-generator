from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NovelCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)


class NovelResponse(BaseModel):
    id: UUID
    title: str
    content_sha256: str
    created_at: datetime


class RunResponse(BaseModel):
    id: UUID
    novel_id: UUID
    kind: str
    status: str
    result_payload: dict[str, object] | None
    error_code: str | None
    cancel_requested: bool


class CharacterResponse(BaseModel):
    id: UUID
    novel_id: UUID
    name: str
    description: str | None
