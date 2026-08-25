import hashlib
import json
from typing import Any, Literal

GroundingStatus = Literal["exact", "fuzzy", "ungrounded"]


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
