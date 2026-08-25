import hashlib
import re
from collections.abc import Iterable, Sequence
from typing import cast
from uuid import UUID, uuid5

from novel_character_generator.domain.entities.document import ChapterBoundary, NormalizedText
from novel_character_generator.domain.entities.retrieval import (
    FusedRetrievalHit,
    RankedPassage,
    RetrievalPassage,
    SearchTerms,
)
from novel_character_generator.domain.policies.text_processing import estimate_tokens

RETRIEVAL_PASSAGE_ALGORITHM_VERSION = "safe-boundary-1k-overlap-v1"
LEXICAL_PROFILE_VERSION = "zh-char-bigram-visual-v1"

VISUAL_TERMS = frozenset(
    {
        "头发",
        "发型",
        "黑发",
        "白发",
        "长发",
        "短发",
        "束发",
        "脸",
        "脸型",
        "面容",
        "容貌",
        "眼睛",
        "眼眸",
        "瞳色",
        "眉",
        "鼻",
        "嘴",
        "胡须",
        "身高",
        "身材",
        "体态",
        "瘦小",
        "高大",
        "衣",
        "白衣",
        "黑衣",
        "长袍",
        "盔甲",
        "服装",
        "饰物",
        "发簪",
        "耳环",
        "项链",
        "腰带",
        "伤疤",
        "伤势",
        "表情",
        "神情",
        "姿态",
        "佩剑",
        "武器",
    }
)

_SAFE_UNIT = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?|\n+")
_TERM_RUN = re.compile(r"[\u3400-\u9fff]+|[A-Za-z0-9_]+")


def _safe_units(text: str, start: int, end: int) -> list[tuple[int, int]]:
    units: list[tuple[int, int]] = []
    for match in _SAFE_UNIT.finditer(text, start, end):
        unit_start = max(start, match.start())
        unit_end = min(end, match.end())
        if unit_end > unit_start and text[unit_start:unit_end].strip():
            units.append((unit_start, unit_end))
    if not units and text[start:end].strip():
        units.append((start, end))
    return units


def _overlap_start(
    text: str,
    units: Sequence[tuple[int, int]],
    group_start: int,
    cursor: int,
    end: int,
    overlap_tokens: int,
) -> int | None:
    if overlap_tokens == 0:
        return None
    candidate_index = cursor
    selected: int | None = None
    while candidate_index > group_start:
        candidate_index -= 1
        candidate_start = units[candidate_index][0]
        if estimate_tokens(text[candidate_start:end]) > overlap_tokens:
            break
        selected = candidate_start
    return selected


def build_retrieval_passages(
    normalized: NormalizedText,
    chapters: Sequence[ChapterBoundary],
    *,
    build_id: UUID,
    target_tokens: int = 1_000,
    overlap_tokens: int = 100,
) -> list[RetrievalPassage]:
    """Split on chapter/sentence boundaries and keep overlap as whole sentences."""
    if target_tokens < 32:
        raise ValueError("retrieval_target_tokens_too_small")
    if overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("invalid_retrieval_overlap_tokens")

    drafts: list[dict[str, object]] = []
    for chapter in chapters:
        units = _safe_units(normalized.text, chapter.normalized_start, chapter.normalized_end)
        cursor = 0
        pending_overlap_start: int | None = None
        while cursor < len(units):
            group_start = cursor
            natural_start = units[cursor][0]
            start = pending_overlap_start if pending_overlap_start is not None else natural_start
            pending_overlap_start = None
            end = units[cursor][1]
            oversized = estimate_tokens(normalized.text[natural_start:end]) > target_tokens
            cursor += 1
            if not oversized:
                while cursor < len(units):
                    candidate_end = units[cursor][1]
                    if estimate_tokens(normalized.text[start:candidate_end]) > target_tokens:
                        break
                    end = candidate_end
                    cursor += 1
            original_start, original_end = normalized.original_span(start, end)
            content = normalized.text[start:end]
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            ordinal = len(drafts)
            passage_id = uuid5(build_id, f"{ordinal}:{start}:{end}:{content_hash}")
            drafts.append(
                {
                    "id": passage_id,
                    "ordinal": ordinal,
                    "chapter_ordinal": chapter.ordinal,
                    "content": content,
                    "content_hash": content_hash,
                    "token_count": estimate_tokens(content),
                    "normalized_start": start,
                    "normalized_end": end,
                    "original_start": original_start,
                    "original_end": original_end,
                    "oversized_sentence": oversized,
                }
            )
            if cursor < len(units):
                pending_overlap_start = _overlap_start(
                    normalized.text,
                    units,
                    group_start,
                    cursor,
                    end,
                    overlap_tokens,
                )

    passages: list[RetrievalPassage] = []
    for index, draft in enumerate(drafts):
        previous_id = cast(UUID, drafts[index - 1]["id"]) if index else None
        next_id = (
            cast(UUID, drafts[index + 1]["id"])
            if index + 1 < len(drafts)
            else None
        )
        passages.append(
            RetrievalPassage(
                **draft,  # type: ignore[arg-type]
                previous_passage_id=previous_id,
                next_passage_id=next_id,
            )
        )
    return passages


def _han_terms(run: str, dictionary: Sequence[str]) -> Iterable[str]:
    yield from run
    for size in (2, 3):
        for index in range(0, len(run) - size + 1):
            yield run[index : index + size]
    for term in dictionary:
        if term and term in run:
            yield term


class ChineseSearchTermBuilder:
    """Deterministic pre-tokenizer for SQLite FTS5 Chinese lexical recall."""

    profile_version = LEXICAL_PROFILE_VERSION

    def __init__(
        self,
        *,
        entity_terms: Iterable[str] = (),
        visual_terms: Iterable[str] = VISUAL_TERMS,
    ) -> None:
        self.entity_dictionary = tuple(
            sorted(set(entity_terms), key=lambda value: (-len(value), value))
        )
        self.visual_dictionary = tuple(
            sorted(set(visual_terms), key=lambda value: (-len(value), value))
        )
        self.dictionary = self.entity_dictionary + self.visual_dictionary

    def build(self, text: str) -> SearchTerms:
        body: list[str] = []
        for match in _TERM_RUN.finditer(text):
            run = match.group(0)
            if run.isascii():
                body.append(run.casefold())
            else:
                body.extend(_han_terms(run, self.dictionary))
        return SearchTerms(
            body_terms=" ".join(dict.fromkeys(body)),
            entity_terms=" ".join(term for term in self.entity_dictionary if term in text),
            visual_terms=" ".join(term for term in self.visual_dictionary if term in text),
        )

    def query(self, text: str) -> str:
        terms = self.build(text)
        prioritized = [*terms.entity_terms.split(), *terms.visual_terms.split()]
        if not prioritized:
            prioritized = [term for term in terms.body_terms.split() if len(term) > 1]
        if not prioritized:
            prioritized = terms.body_terms.split()
        escaped = [term.replace('"', '""') for term in dict.fromkeys(prioritized)]
        return " OR ".join(f'"{term}"' for term in escaped)


def reciprocal_rank_fusion(
    bm25_hits: Sequence[RankedPassage],
    vector_hits: Sequence[RankedPassage],
    *,
    passage_contents: dict[UUID, str],
    entity_terms: Sequence[str] = (),
    rrf_k: int = 60,
    exact_entity_bonus: float = 0.01,
) -> list[FusedRetrievalHit]:
    if rrf_k < 1:
        raise ValueError("rrf_k_must_be_positive")
    combined: dict[UUID, dict[str, float | int | None]] = {}
    for channel, hits in (("bm25", bm25_hits), ("vector", vector_hits)):
        for rank, hit in enumerate(hits, start=1):
            record = combined.setdefault(
                hit.passage_id,
                {
                    "bm25_score": None,
                    "vector_score": None,
                    "bm25_rank": None,
                    "vector_rank": None,
                    "rrf_score": 0.0,
                },
            )
            record[f"{channel}_score"] = hit.score
            record[f"{channel}_rank"] = rank
            record["rrf_score"] = float(record["rrf_score"] or 0.0) + 1.0 / (
                rrf_k + rank
            )

    fused: list[FusedRetrievalHit] = []
    for passage_id, record in combined.items():
        content = passage_contents.get(passage_id, "")
        exact_match = any(term and term in content for term in entity_terms)
        score = float(record["rrf_score"] or 0.0)
        if exact_match:
            score += exact_entity_bonus
        bm25_rank = record["bm25_rank"]
        vector_rank = record["vector_rank"]
        channels = tuple(
            channel
            for channel, rank in (("bm25", bm25_rank), ("vector", vector_rank))
            if rank is not None
        )
        fused.append(
            FusedRetrievalHit(
                passage_id=passage_id,
                source_channels=channels,
                bm25_score=(
                    float(record["bm25_score"])
                    if record["bm25_score"] is not None
                    else None
                ),
                vector_score=(
                    float(record["vector_score"])
                    if record["vector_score"] is not None
                    else None
                ),
                bm25_rank=int(bm25_rank) if bm25_rank is not None else None,
                vector_rank=int(vector_rank) if vector_rank is not None else None,
                rrf_score=score,
                exact_entity_match=exact_match,
            )
        )
    return sorted(
        fused,
        key=lambda hit: (
            -hit.rrf_score,
            hit.bm25_rank or 1_000_000,
            hit.vector_rank or 1_000_000,
            str(hit.passage_id),
        ),
    )
