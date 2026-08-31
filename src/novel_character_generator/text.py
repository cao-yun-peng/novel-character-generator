from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .errors import ContractValidationError


def sha256_text(text: str) -> str:
    """Hash the exact UTF-8 bytes of *text* without normalization."""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, order=True)
class SourceSpan:
    """A half-open interval over decoded Unicode code points."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or not isinstance(self.start, int):
            raise ContractValidationError("span.start must be an integer")
        if isinstance(self.end, bool) or not isinstance(self.end, int):
            raise ContractValidationError("span.end must be an integer")
        if self.start < 0 or self.end <= self.start:
            raise ContractValidationError("span must satisfy 0 <= start < end")

    def validate_container(self, text: str) -> None:
        if self.end > len(text):
            raise ContractValidationError("span exceeds its text container")

    def quote(self, text: str) -> str:
        self.validate_container(text)
        return text[self.start : self.end]

    def to_dict(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}


def find_occurrences(container: str, quote: str) -> tuple[SourceSpan, ...]:
    """Find all occurrences, including overlapping ones, in code-point offsets."""
    if not quote:
        raise ContractValidationError("quote must be a non-empty string")
    spans: list[SourceSpan] = []
    search_from = 0
    while True:
        start = container.find(quote, search_from)
        if start < 0:
            return tuple(spans)
        spans.append(SourceSpan(start, start + len(quote)))
        search_from = start + 1


@dataclass(frozen=True)
class SafeQuoteMatch:
    """A source-backed quote occurrence accepted by the strict grounding rule."""

    raw_quote: str
    span: SourceSpan
    match_mode: str


def _compact_non_whitespace(text: str) -> tuple[str, tuple[int, ...]]:
    characters: list[str] = []
    raw_positions: list[int] = []
    for position, character in enumerate(text):
        if character.isspace():
            continue
        characters.append(character)
        raw_positions.append(position)
    return "".join(characters), tuple(raw_positions)


def find_safe_quote_matches(container: str, model_quote: str) -> tuple[SafeQuoteMatch, ...]:
    """Find exact occurrences, or whitespace-equivalent ones only if exact fails."""
    if not isinstance(container, str):
        raise TypeError("container must be str")
    if not isinstance(model_quote, str) or not model_quote:
        raise ContractValidationError("model_quote must be a non-empty string")

    exact_spans = find_occurrences(container, model_quote)
    if exact_spans:
        return tuple(SafeQuoteMatch(model_quote, span, "exact") for span in exact_spans)

    compact_quote, _ = _compact_non_whitespace(model_quote)
    if not compact_quote:
        return ()
    compact_container, raw_positions = _compact_non_whitespace(container)
    compact_spans = find_occurrences(compact_container, compact_quote)
    matches: list[SafeQuoteMatch] = []
    for compact_span in compact_spans:
        raw_span = SourceSpan(
            raw_positions[compact_span.start],
            raw_positions[compact_span.end - 1] + 1,
        )
        matches.append(
            SafeQuoteMatch(
                raw_quote=raw_span.quote(container),
                span=raw_span,
                match_mode="whitespace_equivalent",
            )
        )
    return tuple(matches)
