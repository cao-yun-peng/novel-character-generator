from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .chunking import DocumentChunkManifest
from .errors import ContractValidationError
from .m2_batch import _parse_source_manifest
from .text import SourceSpan, sha256_text

DOCUMENT_CHARACTER_EVIDENCE_VERSION = "document-character-evidence-v1"
DOCUMENT_FACT_DEDUP_POLICY_VERSION = "document-overlap-safe-fact-dedup-v1"


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


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
    mapping = _mapping(value, label)
    if set(mapping) != {"start", "end"}:
        raise ContractValidationError(f"{label} must contain only start and end")
    return SourceSpan(
        _integer(mapping["start"], f"{label}.start"),
        _integer(mapping["end"], f"{label}.end"),
    )


def _absolute_span(local_span: SourceSpan, chunk_span: SourceSpan, label: str) -> SourceSpan:
    if local_span.end > chunk_span.end - chunk_span.start:
        raise ContractValidationError(f"{label} exceeds its source Chunk")
    return SourceSpan(chunk_span.start + local_span.start, chunk_span.start + local_span.end)


def _validate_quote(text: str, span: SourceSpan, quote: str, label: str) -> None:
    if span.end > len(text) or span.quote(text) != quote:
        raise ContractValidationError(f"{label} does not replay against the document")


def _exact_labels(
    source_n2_packets: Sequence[object],
    *,
    source_document_version_id: str,
) -> dict[tuple[str, str, str], str]:
    labels: dict[tuple[str, str, str], str] = {}
    for packet_index, raw_packet in enumerate(source_n2_packets):
        packet = _mapping(raw_packet, f"source_n2_packets[{packet_index}]")
        if _string(packet.get("source_document_version_id"), "N2 source_document_version_id") != source_document_version_id:
            raise ContractValidationError("N2 packet belongs to a different source document")
        chunk_id = _string(packet.get("chunk_id"), "N2 chunk_id")
        mentions = _sequence(packet.get("grounded_mentions"), "N2 grounded_mentions")
        for mention_index, raw_mention in enumerate(mentions):
            mention = _mapping(raw_mention, f"N2 grounded_mentions[{mention_index}]")
            if mention.get("mention_type") != "exact":
                continue
            local_id = _string(mention.get("local_mention_id"), "N2 exact local_mention_id")
            packet_hash = _string(mention.get("packet_hash"), "N2 exact packet_hash")
            quote = _string(mention.get("mention_quote"), "N2 exact mention_quote")
            key = (chunk_id, local_id, packet_hash)
            if key in labels and labels[key] != quote:
                raise ContractValidationError("one N2 exact character ref resolves to multiple labels")
            labels[key] = quote
    return labels


def _source_occurrence(
    *,
    fact: Mapping[str, object],
    chunk_id: str,
    chunk_hash: str,
    chunk_span: SourceSpan,
    source_character_ref: Mapping[str, object],
    document_text: str,
) -> tuple[dict[str, object], SourceSpan]:
    fact_quote = _string(fact.get("fact_quote"), "fact_quote")
    evidence_quote = _string(fact.get("source_evidence_quote"), "source_evidence_quote")
    local_fact_span = _span(fact.get("fact_chunk_span"), "fact_chunk_span")
    local_evidence_span = _span(fact.get("source_evidence_span"), "source_evidence_span")
    if not (
        local_evidence_span.start <= local_fact_span.start
        and local_fact_span.end <= local_evidence_span.end
    ):
        raise ContractValidationError("fact_chunk_span is outside source_evidence_span")
    document_fact_span = _absolute_span(local_fact_span, chunk_span, "fact_chunk_span")
    document_evidence_span = _absolute_span(local_evidence_span, chunk_span, "source_evidence_span")
    _validate_quote(document_text, document_fact_span, fact_quote, "fact_quote")
    _validate_quote(document_text, document_evidence_span, evidence_quote, "source_evidence_quote")
    return (
        {
            "chunk_id": chunk_id,
            "chunk_hash": chunk_hash,
            "chunk_source_span": chunk_span.to_dict(),
            "source_character_ref": dict(source_character_ref),
            "source_mention_id": _string(fact.get("source_mention_id"), "source_mention_id"),
            "source_mention_type": _string(fact.get("source_mention_type"), "source_mention_type"),
            "source_evidence_quote": evidence_quote,
            "chunk_evidence_span": local_evidence_span.to_dict(),
            "document_evidence_span": document_evidence_span.to_dict(),
            "chunk_fact_span": local_fact_span.to_dict(),
            "match_mode": _string(fact.get("match_mode"), "match_mode"),
        },
        document_fact_span,
    )


def _occurrence_identity(occurrence: Mapping[str, object]) -> str:
    return _canonical_hash(occurrence)


def build_document_character_evidence(
    *,
    document_text: str,
    manifest: DocumentChunkManifest,
    source_n2_packets: Sequence[object],
    n3_target_packets: Sequence[object],
    promotion_grounded_results: Sequence[object],
    source_artifacts: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Convert Chunk-local facts to document spans and safely deduplicate overlap copies."""
    manifest.validate(document_text)
    if source_artifacts is None:
        resolved_source_artifacts: Mapping[str, object] = {
            "m1_manifest": {"path": "in-memory:manifest", "hash": _canonical_hash(manifest.to_dict())},
            "m2_grounded_packets": {
                "path": "in-memory:source-n2-grounded-packets",
                "hash": _canonical_hash(source_n2_packets),
            },
            "n3_target_packets": {
                "path": "in-memory:n3-target-appearance-packets",
                "hash": _canonical_hash(n3_target_packets),
            },
            "promotion_grounded_results": {
                "path": "in-memory:promotion-grounded-results",
                "hash": _canonical_hash(promotion_grounded_results),
            },
        }
    else:
        resolved_source_artifacts = source_artifacts
    entries = {item.chunk_id: item for item in manifest.chunks}
    labels = _exact_labels(
        source_n2_packets,
        source_document_version_id=manifest.source_document_version_id,
    )
    grouped: dict[tuple[object, ...], dict[str, object]] = {}
    input_fact_records = 0

    def add_fact(
        *,
        character_origin: str,
        character_label_quote: str,
        source_character_ref: Mapping[str, object],
        fact: Mapping[str, object],
    ) -> None:
        nonlocal input_fact_records
        input_fact_records += 1
        chunk_id = _string(source_character_ref.get("chunk_id"), "source_character_ref.chunk_id")
        entry = entries.get(chunk_id)
        if entry is None:
            raise ContractValidationError(f"fact references unknown Chunk {chunk_id}")
        chunk_text = entry.chunk_source_span.quote(document_text)
        if character_label_quote not in chunk_text:
            raise ContractValidationError("character label does not occur in its source Chunk")
        occurrence, document_fact_span = _source_occurrence(
            fact=fact,
            chunk_id=chunk_id,
            chunk_hash=entry.chunk_hash,
            chunk_span=entry.chunk_source_span,
            source_character_ref=source_character_ref,
            document_text=document_text,
        )
        fact_quote = _string(fact.get("fact_quote"), "fact_quote")
        category = _string(fact.get("category"), "category")
        attribute = _string(fact.get("attribute"), "attribute")
        value = _string(fact.get("value"), "value")
        identity = (
            character_origin,
            character_label_quote,
            fact_quote,
            document_fact_span.start,
            document_fact_span.end,
            category,
            attribute,
            value,
        )
        if identity not in grouped:
            hash_input = {
                "source_document_version_id": manifest.source_document_version_id,
                "character_origin": character_origin,
                "character_label_quote": character_label_quote,
                "fact_quote": fact_quote,
                "document_fact_span": document_fact_span.to_dict(),
                "category": category,
                "attribute": attribute,
                "value": value,
                "dedup_policy_version": DOCUMENT_FACT_DEDUP_POLICY_VERSION,
            }
            grouped[identity] = {
                "fact_hash": _canonical_hash(hash_input),
                "character_origin": character_origin,
                "character_label_quote": character_label_quote,
                "fact_quote": fact_quote,
                "category": category,
                "attribute": attribute,
                "value": value,
                "document_fact_span": document_fact_span.to_dict(),
                "source_occurrences": [],
            }
        occurrences = grouped[identity]["source_occurrences"]
        if not isinstance(occurrences, list):
            raise AssertionError("source_occurrences invariant broken")
        occurrence_hash = _occurrence_identity(occurrence)
        if all(_occurrence_identity(item) != occurrence_hash for item in occurrences):
            occurrences.append(occurrence)

    for packet_index, raw_packet in enumerate(n3_target_packets):
        packet = _mapping(raw_packet, f"n3_target_packets[{packet_index}]")
        target_ref = _mapping(packet.get("target_character_ref"), "target_character_ref")
        source_version = _string(
            target_ref.get("source_document_version_id"),
            "target_character_ref.source_document_version_id",
        )
        if source_version != manifest.source_document_version_id:
            raise ContractValidationError("N3 target packet belongs to a different source document")
        chunk_id = _string(target_ref.get("chunk_id"), "target_character_ref.chunk_id")
        local_id = _string(target_ref.get("local_mention_id"), "target_character_ref.local_mention_id")
        packet_hash = _string(target_ref.get("packet_hash"), "target_character_ref.packet_hash")
        label = labels.get((chunk_id, local_id, packet_hash))
        if label is None:
            raise ContractValidationError("N3 target ref cannot be resolved to its N2 exact label")
        facts = _sequence(packet.get("grounded_appearance_facts"), "grounded_appearance_facts")
        for fact_index, raw_fact in enumerate(facts):
            add_fact(
                character_origin="exact",
                character_label_quote=label,
                source_character_ref=target_ref,
                fact=_mapping(raw_fact, f"grounded_appearance_facts[{fact_index}]"),
            )

    for result_index, raw_wrapper in enumerate(promotion_grounded_results):
        wrapper = _mapping(raw_wrapper, f"promotion_grounded_results[{result_index}]")
        grounded = _mapping(wrapper.get("grounded_result"), "promotion grounded_result")
        promoted = _sequence(grounded.get("promoted_characters"), "promoted_characters")
        for character_index, raw_character in enumerate(promoted):
            character = _mapping(raw_character, f"promoted_characters[{character_index}]")
            promoted_ref = _mapping(character.get("promoted_character_ref"), "promoted_character_ref")
            source_version = _string(
                promoted_ref.get("source_document_version_id"),
                "promoted_character_ref.source_document_version_id",
            )
            if source_version != manifest.source_document_version_id:
                raise ContractValidationError("promoted character belongs to a different source document")
            label = _string(character.get("character_label_quote"), "character_label_quote")
            facts = _sequence(
                character.get("grounded_belongs_to_character"),
                "grounded_belongs_to_character",
            )
            for fact_index, raw_fact in enumerate(facts):
                add_fact(
                    character_origin="remaining_describe",
                    character_label_quote=label,
                    source_character_ref=promoted_ref,
                    fact=_mapping(raw_fact, f"grounded_belongs_to_character[{fact_index}]"),
                )

    facts = list(grouped.values())
    for item in facts:
        occurrences = item["source_occurrences"]
        if isinstance(occurrences, list):
            occurrences.sort(
                key=lambda occurrence: (
                    _integer(
                        _mapping(occurrence["document_evidence_span"], "document_evidence_span")["start"],
                        "document_evidence_span.start",
                    ),
                    _string(occurrence["chunk_id"], "chunk_id"),
                    _string(occurrence["source_mention_id"], "source_mention_id"),
                )
            )
    facts.sort(
        key=lambda item: (
            _integer(_mapping(item["document_fact_span"], "document_fact_span")["start"], "fact start"),
            _integer(_mapping(item["document_fact_span"], "document_fact_span")["end"], "fact end"),
            _string(item["character_label_quote"], "character_label_quote"),
            _string(item["fact_hash"], "fact_hash"),
        )
    )
    exact_count = sum(item["character_origin"] == "exact" for item in facts)
    promoted_count = len(facts) - exact_count
    source_occurrence_count = sum(len(item["source_occurrences"]) for item in facts)
    return {
        "schema_version": DOCUMENT_CHARACTER_EVIDENCE_VERSION,
        "dedup_policy_version": DOCUMENT_FACT_DEDUP_POLICY_VERSION,
        "source_document_version_id": manifest.source_document_version_id,
        "document_hash": manifest.document_hash,
        "coverage_status": manifest.coverage_status,
        "processed_source_end": manifest.processed_source_end,
        "source_artifacts": dict(resolved_source_artifacts),
        "source_chunks": [entry.to_dict() for entry in manifest.chunks],
        "appearance_facts": facts,
        "summary": {
            "input_fact_records": input_fact_records,
            "document_facts": len(facts),
            "overlap_duplicates_removed": input_fact_records - len(facts),
            "source_occurrences": source_occurrence_count,
            "exact_document_facts": exact_count,
            "promoted_document_facts": promoted_count,
            "source_chunks": len(manifest.chunks),
        },
    }


def run_document_evidence_aggregation(
    *,
    document_text: str,
    source_m1_run_dir: Path,
    source_m2_run_dir: Path,
    source_n3_run_dir: Path,
    output_file: Path,
) -> dict[str, object]:
    manifest_path = source_m1_run_dir / "manifest.json"
    n2_path = source_m2_run_dir / "source-n2-grounded-packets.json"
    n3_path = source_n3_run_dir / "n3-target-appearance-packets.json"
    promotion_path = source_n3_run_dir / "promotion-grounded-results.json"
    manifest = _parse_source_manifest(_read_json(manifest_path), document_text)
    artifacts = {
        "m1_manifest": {"path": str(manifest_path.resolve()), "hash": _file_hash(manifest_path)},
        "m2_grounded_packets": {"path": str(n2_path.resolve()), "hash": _file_hash(n2_path)},
        "n3_target_packets": {"path": str(n3_path.resolve()), "hash": _file_hash(n3_path)},
        "promotion_grounded_results": {
            "path": str(promotion_path.resolve()),
            "hash": _file_hash(promotion_path),
        },
    }
    result = build_document_character_evidence(
        document_text=document_text,
        manifest=manifest,
        source_n2_packets=_sequence(_read_json(n2_path), "source N2 grounded packets"),
        n3_target_packets=_sequence(_read_json(n3_path), "N3 target packets"),
        promotion_grounded_results=_sequence(
            _read_json(promotion_path),
            "promotion grounded results",
        ),
        source_artifacts=artifacts,
    )
    if sha256_text(document_text) != result["document_hash"]:
        raise ContractValidationError("aggregated document hash changed unexpectedly")
    _write_json(output_file, result)
    return result["summary"]
