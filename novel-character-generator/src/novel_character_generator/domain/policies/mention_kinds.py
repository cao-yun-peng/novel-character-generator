from __future__ import annotations

from typing import Literal

MentionKind = Literal["explicit_name", "descriptor", "pronoun", "unknown"]

_LEGACY_MENTION_KIND_ALIASES: dict[str, MentionKind] = {
    "name": "explicit_name",
    "proper_name": "explicit_name",
    "explicit_name": "explicit_name",
    "title": "descriptor",
    "kinship": "descriptor",
    "disguise": "descriptor",
    "nickname": "descriptor",
    "descriptor": "descriptor",
    "pronoun": "pronoun",
    "unknown": "unknown",
}


def normalize_mention_kind(value: object) -> object:
    """Normalize legacy labels without broadening explicit-name semantics."""

    if not isinstance(value, str):
        return value
    token = value.strip().casefold().replace("-", "_").replace(" ", "_")
    return _LEGACY_MENTION_KIND_ALIASES.get(token, value)


def is_explicit_name_mention_kind(value: str) -> bool:
    """Return true only for a proper-name mention, including legacy persisted `name`."""

    return normalize_mention_kind(value) == "explicit_name"
