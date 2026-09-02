from __future__ import annotations

import copy
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

from .document_evidence import (
    DOCUMENT_CHARACTER_EVIDENCE_VERSION,
    DOCUMENT_FACT_DEDUP_POLICY_VERSION,
)
from .errors import ContractValidationError
from .identity import (
    IDENTITY_COMPATIBLE_CANDIDATE_POLICY_VERSIONS,
    IDENTITY_CONFLICT_POLICY_VERSION,
    IDENTITY_POLICY_VERSION,
    IDENTITY_REGISTRY_VERSION,
)
from .text import SourceSpan, sha256_text

DOCUMENT_CHARACTER_PROFILES_VERSION = "document-character-profiles-v1"
DOCUMENT_PROFILE_JOIN_POLICY_VERSION = "strict-fact-hash-profile-join-v1"

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
        raise ContractValidationError(f"cannot read source artifact {path}") from exc


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


def _hash(value: object, label: str) -> str:
    result = _string(value, label)
    if _HASH_PATTERN.fullmatch(result) is None:
        raise ContractValidationError(f"{label} must be a lowercase SHA-256 hash")
    return result


def _artifact(value: object, label: str) -> dict[str, str]:
    raw = _mapping(value, label)
    if set(raw) != {"path", "hash"}:
        raise ContractValidationError(f"{label} must contain only path and hash")
    return {
        "path": _string(raw.get("path"), f"{label}.path"),
        "hash": _hash(raw.get("hash"), f"{label}.hash"),
    }


def _replay(span: SourceSpan, quote: str, document_text: str, label: str) -> None:
    if span.quote(document_text) != quote:
        raise ContractValidationError(f"{label} does not replay the source document")


def _validate_source_occurrence(
    value: object,
    *,
    fact_span: SourceSpan,
    document_text: str,
    label: str,
) -> dict[str, object]:
    occurrence = _mapping(value, label)
    required = {
        "chunk_id",
        "chunk_hash",
        "chunk_source_span",
        "source_character_ref",
        "source_mention_id",
        "source_mention_type",
        "source_evidence_quote",
        "chunk_evidence_span",
        "document_evidence_span",
        "chunk_fact_span",
        "match_mode",
    }
    if set(occurrence) != required:
        raise ContractValidationError(f"{label} fields do not match document-character-evidence-v1")

    chunk_span = _span(occurrence.get("chunk_source_span"), f"{label}.chunk_source_span")
    chunk_text = chunk_span.quote(document_text)
    chunk_hash = _hash(occurrence.get("chunk_hash"), f"{label}.chunk_hash")
    if sha256_text(chunk_text) != chunk_hash:
        raise ContractValidationError(f"{label}.chunk_hash does not match the source document")

    document_evidence_span = _span(
        occurrence.get("document_evidence_span"),
        f"{label}.document_evidence_span",
    )
    evidence_quote = _string(
        occurrence.get("source_evidence_quote"),
        f"{label}.source_evidence_quote",
    )
    _replay(document_evidence_span, evidence_quote, document_text, f"{label}.source_evidence_quote")

    chunk_evidence_span = _span(
        occurrence.get("chunk_evidence_span"),
        f"{label}.chunk_evidence_span",
    )
    chunk_evidence_span.validate_container(chunk_text)
    if chunk_span.start + chunk_evidence_span.start != document_evidence_span.start or (
        chunk_span.start + chunk_evidence_span.end != document_evidence_span.end
    ):
        raise ContractValidationError(f"{label} chunk/document evidence spans disagree")

    chunk_fact_span = _span(occurrence.get("chunk_fact_span"), f"{label}.chunk_fact_span")
    chunk_fact_span.validate_container(chunk_text)
    if chunk_span.start + chunk_fact_span.start != fact_span.start or (
        chunk_span.start + chunk_fact_span.end != fact_span.end
    ):
        raise ContractValidationError(f"{label} chunk/document fact spans disagree")
    if not (
        document_evidence_span.start <= fact_span.start
        and fact_span.end <= document_evidence_span.end
    ):
        raise ContractValidationError(f"{label} fact span is outside its evidence span")

    _string(occurrence.get("chunk_id"), f"{label}.chunk_id")
    _mapping(occurrence.get("source_character_ref"), f"{label}.source_character_ref")
    _string(occurrence.get("source_mention_id"), f"{label}.source_mention_id")
    if occurrence.get("source_mention_type") not in {"exact", "describe"}:
        raise ContractValidationError(f"{label}.source_mention_type is invalid")
    if occurrence.get("match_mode") not in {"exact", "whitespace_equivalent"}:
        raise ContractValidationError(f"{label}.match_mode is invalid")
    return copy.deepcopy(dict(occurrence))


def _validate_fact(
    value: object,
    *,
    index: int,
    source_document_version_id: str,
    dedup_policy_version: str,
    document_text: str,
) -> dict[str, object]:
    label = f"appearance_facts[{index}]"
    fact = _mapping(value, label)
    required = {
        "fact_hash",
        "character_origin",
        "character_label_quote",
        "fact_quote",
        "category",
        "attribute",
        "value",
        "document_fact_span",
        "source_occurrences",
    }
    if set(fact) != required:
        raise ContractValidationError(f"{label} fields do not match document-character-evidence-v1")

    fact_hash = _hash(fact.get("fact_hash"), f"{label}.fact_hash")
    character_origin = _string(fact.get("character_origin"), f"{label}.character_origin")
    if character_origin not in {"exact", "remaining_describe"}:
        raise ContractValidationError(f"{label}.character_origin is invalid")
    character_label = _string(fact.get("character_label_quote"), f"{label}.character_label_quote")
    fact_quote = _string(fact.get("fact_quote"), f"{label}.fact_quote")
    category = _string(fact.get("category"), f"{label}.category")
    attribute = _string(fact.get("attribute"), f"{label}.attribute")
    fact_value = _string(fact.get("value"), f"{label}.value")
    fact_span = _span(fact.get("document_fact_span"), f"{label}.document_fact_span")
    _replay(fact_span, fact_quote, document_text, f"{label}.fact_quote")

    expected_hash = _canonical_hash(
        {
            "source_document_version_id": source_document_version_id,
            "character_origin": character_origin,
            "character_label_quote": character_label,
            "fact_quote": fact_quote,
            "document_fact_span": fact_span.to_dict(),
            "category": category,
            "attribute": attribute,
            "value": fact_value,
            "dedup_policy_version": dedup_policy_version,
        }
    )
    if fact_hash != expected_hash:
        raise ContractValidationError(f"{label}.fact_hash does not match the complete fact")

    raw_occurrences = _sequence(fact.get("source_occurrences"), f"{label}.source_occurrences")
    if not raw_occurrences:
        raise ContractValidationError(f"{label}.source_occurrences must not be empty")
    occurrences = [
        _validate_source_occurrence(
            item,
            fact_span=fact_span,
            document_text=document_text,
            label=f"{label}.source_occurrences[{occurrence_index}]",
        )
        for occurrence_index, item in enumerate(raw_occurrences)
    ]
    result = copy.deepcopy(dict(fact))
    result["source_occurrences"] = occurrences
    return result


def _wrapped_ref_key(value: object, label: str) -> str:
    reference = _mapping(value, label)
    return _canonical_json(reference)


def build_document_character_profiles(
    *,
    document_text: str,
    registry: Mapping[str, object],
    evidence: Mapping[str, object],
    source_artifacts: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Materialize complete document facts under global character identities."""
    if not isinstance(document_text, str):
        raise TypeError("document_text must be str")
    registry = _mapping(registry, "registry")
    evidence = _mapping(evidence, "evidence")
    if registry.get("schema_version") != IDENTITY_REGISTRY_VERSION:
        raise ContractValidationError("registry schema_version is not supported")
    if evidence.get("schema_version") != DOCUMENT_CHARACTER_EVIDENCE_VERSION:
        raise ContractValidationError("evidence schema_version is not supported")

    source_document_version_id = _string(
        registry.get("source_document_version_id"),
        "registry.source_document_version_id",
    )
    if evidence.get("source_document_version_id") != source_document_version_id:
        raise ContractValidationError("registry and evidence belong to different document versions")
    document_hash = _hash(registry.get("document_hash"), "registry.document_hash")
    if evidence.get("document_hash") != document_hash:
        raise ContractValidationError("registry and evidence document hashes differ")
    if sha256_text(document_text) != document_hash:
        raise ContractValidationError("input document does not match registry/evidence document_hash")

    dedup_policy_version = _string(
        evidence.get("dedup_policy_version"),
        "evidence.dedup_policy_version",
    )
    if dedup_policy_version != DOCUMENT_FACT_DEDUP_POLICY_VERSION:
        raise ContractValidationError("evidence dedup_policy_version is not supported")
    coverage_status = _string(evidence.get("coverage_status"), "evidence.coverage_status")
    if coverage_status not in {"complete", "truncated"}:
        raise ContractValidationError("evidence.coverage_status is invalid")
    processed_source_end = _integer(
        evidence.get("processed_source_end"),
        "evidence.processed_source_end",
    )
    if processed_source_end < 0 or processed_source_end > len(document_text):
        raise ContractValidationError("evidence.processed_source_end is outside the document")
    if coverage_status == "complete" and processed_source_end != len(document_text):
        raise ContractValidationError("complete evidence must cover the full document")

    raw_facts = _sequence(evidence.get("appearance_facts"), "evidence.appearance_facts")
    facts_by_hash: dict[str, dict[str, object]] = {}
    for fact_index, raw_fact in enumerate(raw_facts):
        fact = _validate_fact(
            raw_fact,
            index=fact_index,
            source_document_version_id=source_document_version_id,
            dedup_policy_version=dedup_policy_version,
            document_text=document_text,
        )
        fact_hash = str(fact["fact_hash"])
        if fact_hash in facts_by_hash:
            raise ContractValidationError(f"duplicate evidence fact_hash: {fact_hash}")
        facts_by_hash[fact_hash] = fact

    raw_characters = _sequence(registry.get("characters"), "registry.characters")
    character_ids: set[str] = set()
    member_owners: dict[str, str] = {}
    staged_characters: list[tuple[dict[str, object], set[str]]] = []
    assigned_fact_owners: dict[str, str] = {}
    for character_index, raw_character in enumerate(raw_characters):
        label = f"registry.characters[{character_index}]"
        character = _mapping(raw_character, label)
        character_id = _string(character.get("character_id"), f"{label}.character_id")
        if _CHARACTER_ID_PATTERN.fullmatch(character_id) is None:
            raise ContractValidationError(f"{label}.character_id is invalid")
        if character_id in character_ids:
            raise ContractValidationError(f"duplicate character_id: {character_id}")
        character_ids.add(character_id)

        identity_status = _string(character.get("identity_status"), f"{label}.identity_status")
        if identity_status not in {"linked", "singleton"}:
            raise ContractValidationError(f"{label}.identity_status is invalid")
        canonical_label = _string(character.get("canonical_label"), f"{label}.canonical_label")
        canonical_label_status = _string(
            character.get("canonical_label_status"),
            f"{label}.canonical_label_status",
        )
        labels = copy.deepcopy(list(_sequence(character.get("labels"), f"{label}.labels")))
        if not labels:
            raise ContractValidationError(f"{label}.labels must not be empty")
        members = copy.deepcopy(
            list(_sequence(character.get("member_character_refs"), f"{label}.member_character_refs"))
        )
        if not members:
            raise ContractValidationError(f"{label}.member_character_refs must not be empty")
        for member_index, member in enumerate(members):
            key = _wrapped_ref_key(member, f"{label}.member_character_refs[{member_index}]")
            old_owner = member_owners.get(key)
            if old_owner is not None and old_owner != character_id:
                raise ContractValidationError("one member character ref belongs to multiple global characters")
            member_owners[key] = character_id

        appearance_facts: list[dict[str, object]] = []
        character_fact_hashes: set[str] = set()
        fact_refs = _sequence(character.get("appearance_fact_refs"), f"{label}.appearance_fact_refs")
        for ref_index, raw_ref in enumerate(fact_refs):
            ref_label = f"{label}.appearance_fact_refs[{ref_index}]"
            ref = _mapping(raw_ref, ref_label)
            if set(ref) != {"fact_hash", "fact_quote"}:
                raise ContractValidationError(f"{ref_label} must contain only fact_hash and fact_quote")
            fact_hash = _hash(ref.get("fact_hash"), f"{ref_label}.fact_hash")
            if fact_hash in character_fact_hashes:
                raise ContractValidationError(f"duplicate fact ref in {character_id}: {fact_hash}")
            fact = facts_by_hash.get(fact_hash)
            if fact is None:
                raise ContractValidationError(f"registry fact_hash is missing from evidence: {fact_hash}")
            fact_quote = _string(ref.get("fact_quote"), f"{ref_label}.fact_quote")
            if fact_quote != fact["fact_quote"]:
                raise ContractValidationError(f"registry/evidence fact_quote mismatch for {fact_hash}")
            old_owner = assigned_fact_owners.get(fact_hash)
            if old_owner is not None and old_owner != character_id:
                raise ContractValidationError("one fact_hash is assigned to multiple global characters")
            assigned_fact_owners[fact_hash] = character_id
            character_fact_hashes.add(fact_hash)
            appearance_facts.append(copy.deepcopy(fact))
        appearance_facts.sort(
            key=lambda item: (
                _integer(_mapping(item["document_fact_span"], "document_fact_span")["start"], "fact start"),
                _integer(_mapping(item["document_fact_span"], "document_fact_span")["end"], "fact end"),
                str(item["fact_hash"]),
            )
        )

        conflicts = copy.deepcopy(
            list(_sequence(character.get("possible_conflicts"), f"{label}.possible_conflicts"))
        )
        for conflict_index, raw_conflict in enumerate(conflicts):
            conflict = _mapping(raw_conflict, f"{label}.possible_conflicts[{conflict_index}]")
            conflict_hashes = _sequence(
                conflict.get("fact_hashes"),
                f"{label}.possible_conflicts[{conflict_index}].fact_hashes",
            )
            for conflict_hash_index, raw_hash in enumerate(conflict_hashes):
                conflict_hash = _hash(
                    raw_hash,
                    f"{label}.possible_conflicts[{conflict_index}].fact_hashes[{conflict_hash_index}]",
                )
                if conflict_hash not in character_fact_hashes:
                    raise ContractValidationError("possible_conflict references a fact outside its character")

        staged_characters.append(
            (
                {
                    "character_id": character_id,
                    "identity_status": identity_status,
                    "canonical_label": canonical_label,
                    "canonical_label_status": canonical_label_status,
                    "labels": labels,
                    "member_character_refs": members,
                    "appearance_facts": appearance_facts,
                    "possible_conflicts": conflicts,
                    "review_item_ids": [],
                },
                character_fact_hashes,
            )
        )

    review_items = copy.deepcopy(
        list(_sequence(registry.get("review_items"), "registry.review_items"))
    )
    review_ids: set[str] = set()
    review_ids_by_character: dict[str, set[str]] = {item[0]["character_id"]: set() for item in staged_characters}
    for review_index, raw_review in enumerate(review_items):
        label = f"registry.review_items[{review_index}]"
        review = _mapping(raw_review, label)
        review_id = _string(review.get("review_item_id"), f"{label}.review_item_id")
        if review_id in review_ids:
            raise ContractValidationError(f"duplicate review_item_id: {review_id}")
        review_ids.add(review_id)
        subject = review.get("subject_character_ref")
        if subject is not None:
            owner = member_owners.get(_wrapped_ref_key(subject, f"{label}.subject_character_ref"))
            if owner is not None:
                review_ids_by_character[owner].add(review_id)
        for candidate_index, candidate_id_value in enumerate(
            _sequence(review.get("candidate_character_ids"), f"{label}.candidate_character_ids")
        ):
            candidate_id = _string(candidate_id_value, f"{label}.candidate_character_ids[{candidate_index}]")
            if candidate_id not in character_ids:
                raise ContractValidationError(f"review references unknown character_id: {candidate_id}")
            review_ids_by_character[candidate_id].add(review_id)

    characters: list[dict[str, object]] = []
    for character, _ in staged_characters:
        character_id = str(character["character_id"])
        character["review_item_ids"] = sorted(review_ids_by_character[character_id])
        characters.append(character)
    characters.sort(key=lambda item: str(item["character_id"]))

    assigned_hashes = set(assigned_fact_owners)
    unassigned = [copy.deepcopy(fact) for key, fact in facts_by_hash.items() if key not in assigned_hashes]
    unassigned.sort(
        key=lambda item: (
            _integer(_mapping(item["document_fact_span"], "document_fact_span")["start"], "fact start"),
            _integer(_mapping(item["document_fact_span"], "document_fact_span")["end"], "fact end"),
            str(item["fact_hash"]),
        )
    )

    unresolved_bindings = copy.deepcopy(
        list(_sequence(registry.get("unresolved_bindings"), "registry.unresolved_bindings"))
    )
    cannot_link_constraints = copy.deepcopy(
        list(_sequence(registry.get("cannot_link_constraints"), "registry.cannot_link_constraints"))
    )
    if source_artifacts is None:
        artifacts = {
            "character_registry": {
                "path": "memory:document-character-registry.json",
                "hash": _canonical_hash(registry),
            },
            "character_evidence": {
                "path": "memory:document-character-evidence.json",
                "hash": _canonical_hash(evidence),
            },
        }
    else:
        source_artifacts = _mapping(source_artifacts, "source_artifacts")
        if set(source_artifacts) != {"character_registry", "character_evidence"}:
            raise ContractValidationError("source_artifacts must contain registry and evidence")
        artifacts = {
            "character_registry": _artifact(
                source_artifacts.get("character_registry"),
                "source_artifacts.character_registry",
            ),
            "character_evidence": _artifact(
                source_artifacts.get("character_evidence"),
                "source_artifacts.character_evidence",
            ),
        }

    identity_policy_version = _string(
        registry.get("identity_policy_version"),
        "registry.identity_policy_version",
    )
    candidate_policy_version = _string(
        registry.get("candidate_policy_version"),
        "registry.candidate_policy_version",
    )
    conflict_policy_version = _string(
        registry.get("conflict_policy_version"),
        "registry.conflict_policy_version",
    )
    if identity_policy_version != IDENTITY_POLICY_VERSION:
        raise ContractValidationError("registry identity_policy_version is not supported")
    if candidate_policy_version not in IDENTITY_COMPATIBLE_CANDIDATE_POLICY_VERSIONS:
        raise ContractValidationError("registry candidate_policy_version is not supported")
    if conflict_policy_version != IDENTITY_CONFLICT_POLICY_VERSION:
        raise ContractValidationError("registry conflict_policy_version is not supported")

    assigned_facts = [fact for character in characters for fact in character["appearance_facts"]]
    return {
        "schema_version": DOCUMENT_CHARACTER_PROFILES_VERSION,
        "join_policy_version": DOCUMENT_PROFILE_JOIN_POLICY_VERSION,
        "identity_policy_version": identity_policy_version,
        "candidate_policy_version": candidate_policy_version,
        "conflict_policy_version": conflict_policy_version,
        "dedup_policy_version": dedup_policy_version,
        "source_document_version_id": source_document_version_id,
        "document_hash": document_hash,
        "coverage_status": coverage_status,
        "processed_source_end": processed_source_end,
        "source_artifacts": artifacts,
        "characters": characters,
        "unassigned_appearance_facts": unassigned,
        "unresolved_bindings": unresolved_bindings,
        "review_items": review_items,
        "cannot_link_constraints": cannot_link_constraints,
        "summary": {
            "global_characters": len(characters),
            "linked_characters": sum(item["identity_status"] == "linked" for item in characters),
            "singleton_characters": sum(item["identity_status"] == "singleton" for item in characters),
            "characters_with_appearance": sum(bool(item["appearance_facts"]) for item in characters),
            "characters_without_appearance": sum(not item["appearance_facts"] for item in characters),
            "assigned_appearance_facts": len(assigned_facts),
            "unassigned_appearance_facts": len(unassigned),
            "document_appearance_facts": len(facts_by_hash),
            "source_occurrences": sum(len(fact["source_occurrences"]) for fact in facts_by_hash.values()),
            "possible_conflicts": sum(len(item["possible_conflicts"]) for item in characters),
            "review_items": len(review_items),
            "unresolved_bindings": len(unresolved_bindings),
            "cannot_link_constraints": len(cannot_link_constraints),
        },
    }


def run_document_profile_assembly(
    *,
    document_text: str,
    registry_file: Path,
    evidence_file: Path,
    output_file: Path,
) -> dict[str, object]:
    registry = _mapping(_read_json(registry_file), "registry")
    evidence = _mapping(_read_json(evidence_file), "evidence")
    result = build_document_character_profiles(
        document_text=document_text,
        registry=registry,
        evidence=evidence,
        source_artifacts={
            "character_registry": {
                "path": str(registry_file.resolve()),
                "hash": _file_hash(registry_file),
            },
            "character_evidence": {
                "path": str(evidence_file.resolve()),
                "hash": _file_hash(evidence_file),
            },
        },
    )
    _write_json(output_file, result)
    return copy.deepcopy(dict(_mapping(result["summary"], "summary")))
