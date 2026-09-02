from __future__ import annotations

import copy
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

from .document_profiles import DOCUMENT_CHARACTER_PROFILES_VERSION, _validate_fact
from .errors import ContractValidationError
from .identity import IDENTITY_REGISTRY_VERSION
from .m2 import M2_CATEGORIES
from .text import SourceSpan, sha256_text

DOCUMENT_CHARACTER_FACT_GROUPS_VERSION = "document-character-fact-groups-v1"
POST_LINK_FACT_GROUPING_POLICY_VERSION = "same-character-span-structure-v1"
CANONICAL_FACT_GROUPING_REASON = "same_character_span_category_attribute_value"

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CHARACTER_ID_PATTERN = re.compile(r"^char-[0-9a-f]{20}$")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_hash(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"cannot read valid JSON from {path}") from exc


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _file_hash(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ContractValidationError(f"cannot hash fact-group source artifact {path}") from exc


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


def _hash(value: object, label: str) -> str:
    result = _string(value, label)
    if _HASH_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a lowercase SHA-256 hash")
    return result


def _span(value: object, label: str) -> SourceSpan:
    raw = _mapping(value, label)
    if set(raw) != {"start", "end"}:
        raise ContractValidationError(f"{label} must contain only start and end")
    return SourceSpan(
        _integer(raw.get("start"), f"{label}.start"),
        _integer(raw.get("end"), f"{label}.end"),
    )


def _artifact(value: object, label: str) -> dict[str, str]:
    raw = _mapping(value, label)
    if set(raw) != {"path", "hash"}:
        raise ContractValidationError(f"{label} must contain only path and hash")
    return {
        "path": _string(raw.get("path"), f"{label}.path"),
        "hash": _hash(raw.get("hash"), f"{label}.hash"),
    }


def _canonical_fact_id(
    *,
    source_document_version_id: str,
    character_id: str,
    document_fact_span: Mapping[str, int],
    category: str,
    attribute: str,
    value: str,
) -> str:
    return "cfact-" + _canonical_hash(
        {
            "source_document_version_id": source_document_version_id,
            "character_id": character_id,
            "document_fact_span": dict(document_fact_span),
            "category": category,
            "attribute": attribute,
            "value": value,
            "grouping_policy_version": POST_LINK_FACT_GROUPING_POLICY_VERSION,
        }
    )[:20]


def build_document_character_fact_groups(
    *,
    document_text: str,
    registry: Mapping[str, object],
    profiles: Mapping[str, object],
    source_artifacts: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Group post-link raw facts without semantic normalization or source loss."""
    if not isinstance(document_text, str):
        raise TypeError("document_text must be str")
    registry = _mapping(registry, "registry")
    profiles = _mapping(profiles, "profiles")
    if registry.get("schema_version") != IDENTITY_REGISTRY_VERSION:
        raise ContractValidationError("registry schema_version is not supported")
    if profiles.get("schema_version") != DOCUMENT_CHARACTER_PROFILES_VERSION:
        raise ContractValidationError("profiles schema_version is not supported")

    source_document_version_id = _string(
        profiles.get("source_document_version_id"),
        "profiles.source_document_version_id",
    )
    if registry.get("source_document_version_id") != source_document_version_id:
        raise ContractValidationError("registry and profiles belong to different document versions")
    document_hash = _hash(profiles.get("document_hash"), "profiles.document_hash")
    if registry.get("document_hash") != document_hash:
        raise ContractValidationError("registry and profiles document hashes differ")
    if sha256_text(document_text) != document_hash:
        raise ContractValidationError("input document does not match registry/profiles document_hash")

    for policy in ("identity_policy_version", "candidate_policy_version", "conflict_policy_version"):
        if profiles.get(policy) != registry.get(policy):
            raise ContractValidationError(f"registry and profiles {policy} differ")
    dedup_policy_version = _string(
        profiles.get("dedup_policy_version"),
        "profiles.dedup_policy_version",
    )
    coverage_status = _string(profiles.get("coverage_status"), "profiles.coverage_status")
    if coverage_status not in {"complete", "truncated"}:
        raise ContractValidationError("profiles.coverage_status is invalid")
    processed_source_end = _integer(
        profiles.get("processed_source_end"),
        "profiles.processed_source_end",
    )
    if processed_source_end < 0 or processed_source_end > len(document_text):
        raise ContractValidationError("profiles.processed_source_end is outside the document")
    if coverage_status == "complete" and processed_source_end != len(document_text):
        raise ContractValidationError("complete profiles must cover the full document")

    if source_artifacts is None:
        artifacts = {
            "character_registry": {
                "path": "memory:document-character-registry.json",
                "hash": _canonical_hash(registry),
            },
            "character_profiles": {
                "path": "memory:document-character-profiles.json",
                "hash": _canonical_hash(profiles),
            },
        }
    else:
        raw_artifacts = _mapping(source_artifacts, "source_artifacts")
        if set(raw_artifacts) != {"character_registry", "character_profiles"}:
            raise ContractValidationError("source_artifacts must contain registry and profiles")
        artifacts = {
            "character_registry": _artifact(
                raw_artifacts.get("character_registry"),
                "source_artifacts.character_registry",
            ),
            "character_profiles": _artifact(
                raw_artifacts.get("character_profiles"),
                "source_artifacts.character_profiles",
            ),
        }
        profile_sources = _mapping(profiles.get("source_artifacts"), "profiles.source_artifacts")
        recorded_registry = _artifact(
            profile_sources.get("character_registry"),
            "profiles.source_artifacts.character_registry",
        )
        if recorded_registry["hash"] != artifacts["character_registry"]["hash"]:
            raise ContractValidationError("profiles were not built from the supplied registry artifact")

    registry_characters: dict[str, Mapping[str, object]] = {}
    for index, raw_character in enumerate(_sequence(registry.get("characters"), "registry.characters")):
        character = _mapping(raw_character, f"registry.characters[{index}]")
        character_id = _string(character.get("character_id"), f"registry.characters[{index}].character_id")
        if _CHARACTER_ID_PATTERN.fullmatch(character_id) is None or character_id in registry_characters:
            raise ContractValidationError("registry contains invalid or duplicate character_id")
        registry_characters[character_id] = character

    raw_fact_owners: dict[str, str] = {}
    group_members: dict[tuple[object, ...], list[dict[str, object]]] = {}
    output_characters: list[dict[str, object]] = []
    profile_character_ids: set[str] = set()
    validated_fact_index = 0
    assigned_occurrences = 0
    for index, raw_character in enumerate(_sequence(profiles.get("characters"), "profiles.characters")):
        character = _mapping(raw_character, f"profiles.characters[{index}]")
        character_id = _string(character.get("character_id"), f"profiles.characters[{index}].character_id")
        if _CHARACTER_ID_PATTERN.fullmatch(character_id) is None or character_id in profile_character_ids:
            raise ContractValidationError("profiles contain invalid or duplicate character_id")
        profile_character_ids.add(character_id)
        registry_character = registry_characters.get(character_id)
        if registry_character is None:
            raise ContractValidationError("profiles contain character absent from registry")
        for field in ("identity_status", "canonical_label", "canonical_label_status"):
            if character.get(field) != registry_character.get(field):
                raise ContractValidationError(f"registry/profile character {field} differs")

        registry_refs: dict[str, str] = {}
        for ref_index, raw_ref in enumerate(
            _sequence(registry_character.get("appearance_fact_refs"), "registry appearance_fact_refs")
        ):
            ref = _mapping(raw_ref, f"registry appearance_fact_refs[{ref_index}]")
            if set(ref) != {"fact_hash", "fact_quote"}:
                raise ContractValidationError("registry appearance fact ref fields are invalid")
            fact_hash = _hash(ref.get("fact_hash"), "registry fact_hash")
            fact_quote = _string(ref.get("fact_quote"), "registry fact_quote")
            if fact_hash in registry_refs:
                raise ContractValidationError("registry character contains duplicate fact ref")
            registry_refs[fact_hash] = fact_quote

        profile_hashes: set[str] = set()
        for raw_fact in _sequence(character.get("appearance_facts"), "profile appearance_facts"):
            fact = _validate_fact(
                raw_fact,
                index=validated_fact_index,
                source_document_version_id=source_document_version_id,
                dedup_policy_version=dedup_policy_version,
                document_text=document_text,
            )
            validated_fact_index += 1
            fact_hash = str(fact["fact_hash"])
            if fact["category"] not in M2_CATEGORIES:
                raise ContractValidationError("profile fact category is unsupported")
            if fact_hash in raw_fact_owners:
                raise ContractValidationError("one raw fact_hash appears under multiple profile entries")
            raw_fact_owners[fact_hash] = character_id
            if registry_refs.get(fact_hash) != fact["fact_quote"]:
                raise ContractValidationError("registry/profile raw fact ownership or quote differs")
            profile_hashes.add(fact_hash)
            span = _mapping(fact["document_fact_span"], "fact.document_fact_span")
            key = (
                character_id,
                _integer(span.get("start"), "fact span start"),
                _integer(span.get("end"), "fact span end"),
                str(fact["category"]),
                str(fact["attribute"]),
                str(fact["value"]),
            )
            group_members.setdefault(key, []).append(fact)
            assigned_occurrences += len(_sequence(fact["source_occurrences"], "source_occurrences"))
        if profile_hashes != set(registry_refs):
            raise ContractValidationError("registry/profile fact sets differ for character")
        output_characters.append(
            {
                "character_id": character_id,
                "identity_status": _string(character.get("identity_status"), "profile identity_status"),
                "canonical_label": _string(character.get("canonical_label"), "profile canonical_label"),
                "canonical_fact_ids": [],
            }
        )
    if profile_character_ids != set(registry_characters):
        raise ContractValidationError("registry and profiles character sets differ")

    canonical_groups: list[dict[str, object]] = []
    ids_by_character: dict[str, list[str]] = {item["character_id"]: [] for item in output_characters}
    for key, facts in sorted(group_members.items(), key=lambda item: item[0]):
        character_id, start, end, category, attribute, value = key
        fact_quotes = {str(fact["fact_quote"]) for fact in facts}
        if len(fact_quotes) != 1:
            raise ContractValidationError("one structural group has inconsistent fact_quote values")
        span = {"start": start, "end": end}
        fact_id = _canonical_fact_id(
            source_document_version_id=source_document_version_id,
            character_id=str(character_id),
            document_fact_span=span,
            category=str(category),
            attribute=str(attribute),
            value=str(value),
        )
        occurrence_bindings: list[dict[str, object]] = []
        for fact in sorted(facts, key=lambda item: str(item["fact_hash"])):
            for occurrence_index, occurrence in enumerate(
                _sequence(fact["source_occurrences"], "fact.source_occurrences")
            ):
                occurrence_bindings.append(
                    {
                        "source_fact_hash": fact["fact_hash"],
                        "source_occurrence_index": occurrence_index,
                        "source_occurrence": copy.deepcopy(occurrence),
                    }
                )
        group = {
            "canonical_fact_id": fact_id,
            "character_id": character_id,
            "fact_quote": next(iter(fact_quotes)),
            "category": category,
            "attribute": attribute,
            "value": value,
            "document_fact_span": span,
            "source_fact_hashes": sorted(str(fact["fact_hash"]) for fact in facts),
            "source_occurrences": occurrence_bindings,
            "grouping_reason": CANONICAL_FACT_GROUPING_REASON,
            "scope_assignment_status": "unassigned",
        }
        canonical_groups.append(group)
        ids_by_character[str(character_id)].append(fact_id)

    unassigned_facts: list[dict[str, object]] = []
    unassigned_occurrence_bindings: list[dict[str, object]] = []
    unassigned_occurrences = 0
    for raw_fact in _sequence(
        profiles.get("unassigned_appearance_facts"),
        "profiles.unassigned_appearance_facts",
    ):
        fact = _validate_fact(
            raw_fact,
            index=validated_fact_index,
            source_document_version_id=source_document_version_id,
            dedup_policy_version=dedup_policy_version,
            document_text=document_text,
        )
        validated_fact_index += 1
        fact_hash = str(fact["fact_hash"])
        if fact["category"] not in M2_CATEGORIES:
            raise ContractValidationError("unassigned profile fact category is unsupported")
        if fact_hash in raw_fact_owners:
            raise ContractValidationError("unassigned raw fact_hash duplicates an assigned fact")
        raw_fact_owners[fact_hash] = "unassigned"
        unassigned_facts.append(fact)
        occurrences = _sequence(fact["source_occurrences"], "source_occurrences")
        unassigned_occurrences += len(occurrences)
        for occurrence_index, occurrence in enumerate(occurrences):
            unassigned_occurrence_bindings.append(
                {
                    "source_fact_hash": fact_hash,
                    "source_occurrence_index": occurrence_index,
                    "source_occurrence": copy.deepcopy(occurrence),
                }
            )

    for character in output_characters:
        character["canonical_fact_ids"] = ids_by_character[str(character["character_id"])]
    output_characters.sort(key=lambda item: str(item["character_id"]))

    profile_summary = _mapping(profiles.get("summary"), "profiles.summary")
    assigned_count = len(raw_fact_owners) - len(unassigned_facts)
    occurrence_count = assigned_occurrences + unassigned_occurrences
    expected_summary = {
        "assigned_appearance_facts": assigned_count,
        "unassigned_appearance_facts": len(unassigned_facts),
        "document_appearance_facts": len(raw_fact_owners),
        "source_occurrences": occurrence_count,
    }
    for field, expected in expected_summary.items():
        if profile_summary.get(field) != expected:
            raise ContractValidationError(f"profiles summary {field} is inconsistent")

    return {
        "schema_version": DOCUMENT_CHARACTER_FACT_GROUPS_VERSION,
        "grouping_policy_version": POST_LINK_FACT_GROUPING_POLICY_VERSION,
        "source_document_version_id": source_document_version_id,
        "document_hash": document_hash,
        "coverage_status": coverage_status,
        "processed_source_end": processed_source_end,
        "source_artifacts": artifacts,
        "characters": output_characters,
        "fact_groups": canonical_groups,
        "unassigned_source_fact_hashes": sorted(str(fact["fact_hash"]) for fact in unassigned_facts),
        "unassigned_source_occurrences": unassigned_occurrence_bindings,
        "summary": {
            "characters": len(output_characters),
            "characters_with_fact_groups": sum(bool(item["canonical_fact_ids"]) for item in output_characters),
            "raw_appearance_facts": len(raw_fact_owners),
            "assigned_raw_appearance_facts": assigned_count,
            "unassigned_raw_appearance_facts": len(unassigned_facts),
            "canonical_fact_groups": len(canonical_groups),
            "multi_member_fact_groups": sum(len(item["source_fact_hashes"]) > 1 for item in canonical_groups),
            "collapsed_raw_fact_members": assigned_count - len(canonical_groups),
            "source_occurrences": occurrence_count,
            "provider_calls": 0,
            "complete": True,
        },
    }


def run_document_fact_group_assembly(
    *,
    document_text: str,
    registry_file: Path,
    profiles_file: Path,
    output_file: Path,
) -> dict[str, object]:
    registry = _mapping(_read_json(registry_file), "registry")
    profiles = _mapping(_read_json(profiles_file), "profiles")
    result = build_document_character_fact_groups(
        document_text=document_text,
        registry=registry,
        profiles=profiles,
        source_artifacts={
            "character_registry": {
                "path": str(registry_file.resolve()),
                "hash": _file_hash(registry_file),
            },
            "character_profiles": {
                "path": str(profiles_file.resolve()),
                "hash": _file_hash(profiles_file),
            },
        },
    )
    _write_json(output_file, result)
    return copy.deepcopy(dict(_mapping(result["summary"], "summary")))
