from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RetrievalPassage:
    """A rebuildable, fine-grained view over one immutable source version."""

    id: UUID
    ordinal: int
    chapter_ordinal: int
    content: str
    content_hash: str
    token_count: int
    normalized_start: int
    normalized_end: int
    original_start: int
    original_end: int
    previous_passage_id: UUID | None
    next_passage_id: UUID | None
    oversized_sentence: bool


@dataclass(frozen=True)
class SearchTerms:
    body_terms: str
    entity_terms: str
    visual_terms: str


@dataclass(frozen=True)
class RankedPassage:
    passage_id: UUID
    score: float


@dataclass(frozen=True)
class FusedRetrievalHit:
    passage_id: UUID
    source_channels: tuple[str, ...]
    bm25_score: float | None
    vector_score: float | None
    bm25_rank: int | None
    vector_rank: int | None
    rrf_score: float
    exact_entity_match: bool


@dataclass(frozen=True)
class RetrievalHit:
    passage_id: UUID
    source_channels: tuple[str, ...]
    bm25_score: float | None
    vector_score: float | None
    bm25_rank: int | None
    vector_rank: int | None
    rrf_score: float
    exact_entity_match: bool
    expansion_reason: str | None
    final_rank: int
    selected: bool
