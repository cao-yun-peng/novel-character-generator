from pydantic import BaseModel, Field


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
