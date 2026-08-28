import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

GroundingStatus = Literal["exact", "fuzzy", "ungrounded"]
EvidenceLocationStatus = Literal["exact", "normalized", "repaired", "ambiguous", "not_found"]
EvidenceRepairKind = Literal["whitespace_or_punctuation", "single_character_omission"]

_NARROW_OMISSION_CHARACTERS = frozenset("一的地得了着之其所而于有在")
_IGNORABLE_PUNCTUATION = frozenset(",，、:：'‘’\"“”（）()【】[]《》<>—-…")


@dataclass(frozen=True)
class EvidenceLocation:
    status: EvidenceLocationStatus
    start: int | None = None
    end: int | None = None
    source_quote: str | None = None
    occurrence_count: int = 0
    repair_kind: EvidenceRepairKind | None = None


def _occurrences(text: str, quote: str) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    cursor = 0
    while quote and cursor <= len(text) - len(quote):
        start = text.find(quote, cursor)
        if start < 0:
            break
        matches.append((start, start + len(quote)))
        cursor = start + 1
    return matches


def _nearest_unique_match(
    text: str,
    matches: list[tuple[int, int]],
    anchors: list[tuple[int, int]],
) -> tuple[int, int] | None:
    if not matches or not anchors:
        return None
    ranked: list[tuple[tuple[int, float], tuple[int, int]]] = []
    for match in matches:
        center = (match[0] + match[1]) / 2
        scores: list[tuple[int, float]] = []
        for anchor in anchors:
            gap_start = min(match[1], anchor[1])
            gap_end = max(match[0], anchor[0])
            boundary_count = sum(
                text.count(boundary, gap_start, gap_end)
                for boundary in "。！？!?；;\n"
            )
            distance = abs(center - ((anchor[0] + anchor[1]) / 2))
            scores.append((boundary_count, distance))
        ranked.append((min(scores), match))
    ranked.sort(key=lambda item: item[0])
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def _collapsed_surface(value: str) -> tuple[str, list[int]]:
    normalized: list[str] = []
    source_indices: list[int] = []
    for index, character in enumerate(value):
        if character.isspace() or character in _IGNORABLE_PUNCTUATION:
            continue
        normalized.append(character)
        source_indices.append(index)
    return "".join(normalized), source_indices


def _narrow_omission_matches(text: str, quote: str) -> list[tuple[int, int]]:
    """Find spans where the provider omitted exactly one low-information character."""

    window_size = len(quote) + 1
    if not quote or window_size > len(text):
        return []
    matches: set[tuple[int, int]] = set()
    for start in range(0, len(text) - window_size + 1):
        window = text[start : start + window_size]
        for omitted_index, omitted_character in enumerate(window):
            if omitted_character not in _NARROW_OMISSION_CHARACTERS:
                continue
            if window[:omitted_index] + window[omitted_index + 1 :] == quote:
                matches.add((start, start + window_size))
    return sorted(matches)


def locate_evidence_span(
    text: str,
    quote: str,
    *,
    anchor_quote: str | None = None,
) -> EvidenceLocation:
    """Locate a provider quote deterministically without trusting model offsets.

    Exact unique matches are preferred. Repeated quotes may be disambiguated only
    when one occurrence is uniquely nearest to an entity anchor. The sole tolerant
    First fallback ignores whitespace and punctuation while preserving a mapping to the original
    source. The final fallback repairs one omitted low-information character only when the source
    span is unique. Semantic substitutions and ambiguous repairs remain rejected.
    """

    if not quote.strip():
        return EvidenceLocation(status="not_found")
    matches = _occurrences(text, quote)
    anchors = _occurrences(text, anchor_quote) if anchor_quote else []
    if len(matches) == 1:
        start, end = matches[0]
        return EvidenceLocation("exact", start, end, text[start:end], 1)
    if len(matches) > 1:
        selected = _nearest_unique_match(text, matches, anchors)
        if selected is not None:
            start, end = selected
            return EvidenceLocation("exact", start, end, text[start:end], len(matches))
        return EvidenceLocation(status="ambiguous", occurrence_count=len(matches))

    normalized_text, source_indices = _collapsed_surface(text)
    normalized_quote, _ = _collapsed_surface(quote)
    if not normalized_quote:
        return EvidenceLocation(status="not_found")
    normalized_matches = _occurrences(normalized_text, normalized_quote)
    if len(normalized_matches) > 1:
        return EvidenceLocation(
            status="ambiguous",
            occurrence_count=len(normalized_matches),
        )
    if len(normalized_matches) == 1 and source_indices:
        normalized_start, normalized_end = normalized_matches[0]
        start = source_indices[normalized_start]
        end = source_indices[normalized_end - 1] + 1
        return EvidenceLocation(
            "normalized",
            start,
            end,
            text[start:end],
            1,
            "whitespace_or_punctuation",
        )

    repaired_matches = _narrow_omission_matches(normalized_text, normalized_quote)
    if len(repaired_matches) != 1 or not source_indices:
        return EvidenceLocation(
            status="ambiguous" if len(repaired_matches) > 1 else "not_found",
            occurrence_count=len(repaired_matches),
        )
    repaired_start, repaired_end = repaired_matches[0]
    start = source_indices[repaired_start]
    end = source_indices[repaired_end - 1] + 1
    return EvidenceLocation(
        "repaired",
        start,
        end,
        text[start:end],
        1,
        "single_character_omission",
    )


def validate_evidence(text: str, quote: str, start: int, end: int) -> GroundingStatus:
    if start < 0 or end <= start or end > len(text):
        return "ungrounded"
    if text[start:end] == quote:
        return "exact"
    if quote.strip() and quote.strip() in text[max(0, start - 20) : min(len(text), end + 20)]:
        return "fuzzy"
    return "ungrounded"


def repair_evidence_span(
    text: str, quote: str, start: int, end: int
) -> tuple[int, int, GroundingStatus]:
    grounding = validate_evidence(text, quote, start, end)
    if grounding == "exact":
        return start, end, grounding
    if not quote:
        return start, end, grounding
    first = text.find(quote)
    if first < 0 or text.find(quote, first + 1) >= 0:
        return start, end, grounding
    repaired_end = first + len(quote)
    return first, repaired_end, "exact"


def observation_fingerprint(
    *,
    source_version: str,
    start: int,
    end: int,
    field_path: str,
    value: Any,
    extractor_version: str,
) -> str:
    payload = json.dumps(
        [source_version, start, end, field_path, value, extractor_version],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()
