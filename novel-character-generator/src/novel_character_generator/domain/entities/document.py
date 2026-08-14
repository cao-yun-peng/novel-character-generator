from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SourceDocumentVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_document_id: UUID
    version: int = Field(ge=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    storage_uri: str
    encoding: str
    normalization_map_id: UUID | None = None
    supersedes_version_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NormalizationMap(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_document_version_id: UUID
    algorithm_version: str
    original_boundaries: list[int]


class NormalizedText(BaseModel):
    text: str
    original_boundaries: list[int]
    map_version: str

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        if start < 0 or end <= start or end >= len(self.original_boundaries):
            raise ValueError("invalid normalized span")
        return self.original_boundaries[start], self.original_boundaries[end]


class ChapterBoundary(BaseModel):
    ordinal: int = Field(ge=0)
    title: str | None
    normalized_start: int = Field(ge=0)
    normalized_end: int = Field(gt=0)


class TextChunk(BaseModel):
    ordinal: int = Field(ge=0)
    chapter_ordinal: int = Field(ge=0)
    content: str
    content_hash: str
    normalized_start: int = Field(ge=0)
    normalized_end: int = Field(gt=0)
    original_start: int = Field(ge=0)
    original_end: int = Field(gt=0)
