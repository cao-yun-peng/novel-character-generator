from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from .errors import ContractValidationError
from .fact_groups import DOCUMENT_CHARACTER_FACT_GROUPS_VERSION
from .text import SourceSpan, sha256_text

DOCUMENT_CHARACTER_APPEARANCE_SCOPES_VERSION = "document-character-appearance-scopes-v1"
APPEARANCE_SCOPE_POLICY_VERSION = "chapter-order-conservative-persistence-v1"

_CHAPTER_PATTERN = re.compile(
    r"(?m)^[\u3000 \t]*第(?P<number>[0-9零〇一二三四五六七八九十百千两]+)章[ \t]*(?P<title>[^\r\n]*)"
)
_CANONICAL_FACT_ID_PATTERN = re.compile(r"^cfact-[0-9a-f]{20}$")
_CHARACTER_ID_PATTERN = re.compile(r"^char-[0-9a-f]{20}$")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractValidationError(f"{label} must be an integer")
    return value


def _span(value: object, label: str) -> SourceSpan:
    raw = _mapping(value, label)
    if set(raw) != {"start", "end"}:
        raise ContractValidationError(f"{label} must contain only start and end")
    return SourceSpan(
        _integer(raw.get("start"), f"{label}.start"),
        _integer(raw.get("end"), f"{label}.end"),
    )


def _chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    for character in value:
        if character in digits:
            current = digits[character]
        elif character in units:
            unit = units[character]
            total += (current or 1) * unit
            current = 0
        else:
            raise ContractValidationError(f"unsupported chapter number: {value}")
    result = total + current
    if result < 1:
        raise ContractValidationError(f"chapter number must be positive: {value}")
    return result


def parse_document_chapters(document_text: str) -> list[dict[str, object]]:
    """Parse chapter boundaries and collapse only adjacent duplicate headings."""
    if not isinstance(document_text, str) or not document_text:
        raise ContractValidationError("document_text must be non-empty")
    matches = list(_CHAPTER_PATTERN.finditer(document_text))
    boundaries: list[tuple[int, int, str, int]] = []
    for match in matches:
        number = _chinese_number(match.group("number"))
        title = match.group("title").strip()
        if boundaries:
            previous_start, previous_number, previous_title, previous_end = boundaries[-1]
            between = document_text[previous_end : match.start()]
            if number == previous_number and title == previous_title and not between.strip():
                boundaries[-1] = (previous_start, previous_number, previous_title, match.end())
                continue
        boundaries.append((match.start(), number, title, match.end()))

    if not boundaries:
        return [{"chapter_number": 0, "title": "", "document_span": {"start": 0, "end": len(document_text)}}]
    if boundaries[0][0] > 0 and document_text[: boundaries[0][0]].strip():
        boundaries.insert(0, (0, 0, "", 0))

    chapters: list[dict[str, object]] = []
    for index, (start, number, title, _) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(document_text)
        chapters.append(
            {
                "chapter_number": number,
                "title": title,
                "document_span": {"start": start, "end": end},
            }
        )
    return chapters


def _persistence(category: str) -> str:
    if category == "age":
        return "persistent_until_changed"
    if category == "distinctive_mark":
        return "stable"
    if category in {"clothing", "accessory"}:
        return "scene"
    if category == "appearance_state":
        return "momentary"
    return "unknown"


def build_document_character_appearance_scopes(
    *,
    document_text: str,
    fact_groups: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(document_text, str) or not document_text:
        raise ContractValidationError("document_text must be non-empty")
    fact_groups = _mapping(fact_groups, "fact_groups")
    if fact_groups.get("schema_version") != DOCUMENT_CHARACTER_FACT_GROUPS_VERSION:
        raise ContractValidationError("fact_groups schema_version is not supported")
    source_document_version_id = _string(
        fact_groups.get("source_document_version_id"),
        "fact_groups.source_document_version_id",
    )
    if fact_groups.get("document_hash") != sha256_text(document_text):
        raise ContractValidationError("input document does not match fact_groups document_hash")
    coverage_status = _string(fact_groups.get("coverage_status"), "fact_groups.coverage_status")
    processed_source_end = _integer(
        fact_groups.get("processed_source_end"),
        "fact_groups.processed_source_end",
    )
    if coverage_status not in {"complete", "truncated"}:
        raise ContractValidationError("fact_groups coverage_status is invalid")
    if not 0 < processed_source_end <= len(document_text):
        raise ContractValidationError("processed_source_end is outside the document")
    if coverage_status == "complete" and processed_source_end != len(document_text):
        raise ContractValidationError("complete fact_groups must cover the document")

    chapters = parse_document_chapters(document_text[:processed_source_end])
    chapter_spans = [
        (
            item["chapter_number"],
            _span(item["document_span"], "chapter.document_span"),
        )
        for item in chapters
    ]
    assignments: list[dict[str, object]] = []
    seen_fact_ids: set[str] = set()
    character_fact_ids: dict[str, set[str]] = {}
    for index, raw_character in enumerate(_sequence(fact_groups.get("characters"), "fact_groups.characters")):
        character = _mapping(raw_character, f"fact_groups.characters[{index}]")
        character_id = _string(character.get("character_id"), "character_id")
        if _CHARACTER_ID_PATTERN.fullmatch(character_id) is None or character_id in character_fact_ids:
            raise ContractValidationError("fact_groups contain invalid or duplicate character_id")
        ids = {
            _string(item, "canonical_fact_ids[]")
            for item in _sequence(character.get("canonical_fact_ids"), "canonical_fact_ids")
        }
        if any(_CANONICAL_FACT_ID_PATTERN.fullmatch(item) is None for item in ids):
            raise ContractValidationError("character contains invalid canonical_fact_id")
        character_fact_ids[character_id] = ids
    seen_character_ids = set(character_fact_ids)
    positions_by_id: dict[str, int] = {}
    actual_ids_by_character: dict[str, set[str]] = {character_id: set() for character_id in seen_character_ids}
    for index, raw_fact in enumerate(_sequence(fact_groups.get("fact_groups"), "fact_groups.fact_groups")):
        fact = _mapping(raw_fact, f"fact_groups.fact_groups[{index}]")
        fact_id = _string(fact.get("canonical_fact_id"), "canonical_fact_id")
        character_id = _string(fact.get("character_id"), "character_id")
        if _CANONICAL_FACT_ID_PATTERN.fullmatch(fact_id) is None or fact_id in seen_fact_ids:
            raise ContractValidationError("fact_groups contain invalid or duplicate canonical_fact_id")
        if _CHARACTER_ID_PATTERN.fullmatch(character_id) is None or character_id not in seen_character_ids:
            raise ContractValidationError("fact_group character_id is invalid or unknown")
        seen_fact_ids.add(fact_id)
        actual_ids_by_character[character_id].add(fact_id)
        fact_span = _span(fact.get("document_fact_span"), "document_fact_span")
        if fact_span.end > processed_source_end:
            raise ContractValidationError("fact span exceeds processed source coverage")
        if fact_span.quote(document_text) != _string(fact.get("fact_quote"), "fact_quote"):
            raise ContractValidationError("fact_quote does not replay at document_fact_span")
        positions_by_id[fact_id] = fact_span.start
        chapter_number = next(
            (
                number
                for number, chapter_span in chapter_spans
                if chapter_span.start <= fact_span.start < chapter_span.end
            ),
            None,
        )
        if chapter_number is None:
            raise ContractValidationError("fact cannot be assigned to a chapter")
        category = _string(fact.get("category"), "category")
        assignments.append(
            {
                "canonical_fact_id": fact_id,
                "character_id": character_id,
                "chapter_number": chapter_number,
                "order": 0,
                "life": "unknown",
                "form": "unknown",
                "scene": "unknown",
                "persistence": _persistence(category),
            }
        )

    if actual_ids_by_character != character_fact_ids:
        raise ContractValidationError("character canonical_fact_ids do not match fact_groups")
    assignments.sort(key=lambda item: (positions_by_id[str(item["canonical_fact_id"])], str(item["canonical_fact_id"])))
    for order, assignment in enumerate(assignments):
        assignment["order"] = order

    summary = _mapping(fact_groups.get("summary"), "fact_groups.summary")
    if summary.get("canonical_fact_groups") != len(assignments):
        raise ContractValidationError("fact_groups summary canonical_fact_groups is inconsistent")
    persistence_counts = {
        value: sum(item["persistence"] == value for item in assignments)
        for value in ("stable", "persistent_until_changed", "scene", "momentary", "unknown")
    }
    return {
        "schema_version": DOCUMENT_CHARACTER_APPEARANCE_SCOPES_VERSION,
        "scope_policy_version": APPEARANCE_SCOPE_POLICY_VERSION,
        "source_document_version_id": source_document_version_id,
        "coverage_status": coverage_status,
        "processed_source_end": processed_source_end,
        "chapters": chapters,
        "fact_assignments": assignments,
        "summary": {
            "chapters": len(chapters),
            "canonical_facts": len(assignments),
            "unknown_life": len(assignments),
            "unknown_form": len(assignments),
            "unknown_scene": len(assignments),
            "stable": persistence_counts["stable"],
            "persistent_until_changed": persistence_counts["persistent_until_changed"],
            "scene": persistence_counts["scene"],
            "momentary": persistence_counts["momentary"],
            "unknown_persistence": persistence_counts["unknown"],
            "provider_calls": 0,
            "complete": True,
        },
    }


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"cannot read valid JSON from {path}") from exc


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_document_appearance_scope_assembly(
    *,
    document_text: str,
    fact_groups_file: Path,
    output_file: Path,
) -> dict[str, object]:
    result = build_document_character_appearance_scopes(
        document_text=document_text,
        fact_groups=_read_json(fact_groups_file),
    )
    _write_json(output_file, result)
    return copy.deepcopy(dict(_mapping(result["summary"], "summary")))
