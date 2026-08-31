from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from .chunking import build_document_chunk_manifest
from .errors import ContractValidationError, ProviderError
from .grounding import ground_m1_result
from .m1 import M1OrchestrationEnvelope, M1Orchestrator, M1Provider
from .providers import DeepSeekCallTrace
from .text import sha256_text


ProgressSink = Callable[[str], None]
M1_CHUNK_RESULT_VERSION = "m1-chunk-result-v4"
M1_BATCH_SUMMARY_VERSION = "m1-batch-summary-v3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_trace(
    traces: Sequence[DeepSeekCallTrace] | None,
    previous_count: int,
) -> dict[str, object] | None:
    if traces is None or len(traces) <= previous_count:
        return None
    return traces[-1].to_dict()


def _sum_optional(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _build_summary(
    *,
    started_at: str,
    duration_ms: int,
    manifest: dict[str, object],
    records: list[dict[str, object]],
    failures: list[dict[str, object]],
    resumed_chunks: int,
    new_provider_calls: int,
) -> dict[str, object]:
    traces = [record.get("provider_trace") for record in records]
    trace_dicts = [trace for trace in traces if isinstance(trace, dict)]
    usage_dicts = [trace.get("usage") for trace in trace_dicts]
    usages = [usage for usage in usage_dicts if isinstance(usage, dict)]
    outputs = [record["model_output"] for record in records]
    candidates = [
        candidate
        for output in outputs
        if isinstance(output, dict)
        for candidate in output.get("candidate_mentions", [])
        if isinstance(candidate, dict)
    ]
    packets = [record["grounded_packet"] for record in records]
    grounded = [
        mention
        for packet in packets
        if isinstance(packet, dict)
        for mention in packet.get("grounded_mentions", [])
        if isinstance(mention, dict)
    ]
    rejected = [
        evidence
        for packet in packets
        if isinstance(packet, dict)
        for evidence in packet.get("rejected_evidence", [])
        if isinstance(evidence, dict)
    ]
    trace_events = [
        event
        for record in records
        for event in record.get("grounding_trace_events", [])
        if isinstance(event, dict)
    ]
    approved_count = sum(
        len(mention.get("approved_evidence", []))
        for mention in grounded
        if isinstance(mention.get("approved_evidence", []), list)
    )
    mention_types = {"exact": 0, "describe": 0, "null": 0}
    for candidate in candidates:
        value = candidate.get("mention_type")
        mention_types["null" if value is None else str(value)] += 1
    models = sorted(
        {
            str(trace["model"])
            for trace in trace_dicts
            if isinstance(trace.get("model"), str)
        }
    )
    usage = {
        key: _sum_optional(
            [item.get(key) if isinstance(item.get(key), int) else None for item in usages]
        )
        for key in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
        )
    }
    return {
        "schema_version": M1_BATCH_SUMMARY_VERSION,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "duration_ms": duration_ms,
        "source_document_version_id": manifest["source_document_version_id"],
        "document_hash": manifest["document_hash"],
        "total_characters": manifest["total_characters"],
        "chunking_policy_version": manifest["chunking_policy_version"],
        "planned_chunks": len(manifest["chunks"]),
        "succeeded_chunks": len(records),
        "failed_chunks": len(failures),
        "resumed_chunks": resumed_chunks,
        "new_provider_calls": new_provider_calls,
        "models": models,
        "candidate_mentions": len(candidates),
        "candidate_mentions_by_type": mention_types,
        "grounded_mentions": len(grounded),
        "approved_evidence_quotes": approved_count,
        "rejected_evidence_quotes": len(rejected),
        "grounding_trace_events": len(trace_events),
        "exact_evidence_precedence": {
            "shadowed_describe_evidence": sum(
                event.get("code") == "describe_evidence_shadowed_by_exact"
                for event in trace_events
            ),
            "removed_empty_describe_blocks": sum(
                event.get("code") == "describe_removed_after_exact_dedup"
                for event in trace_events
            ),
        },
        "usage": usage,
        "complete": len(records) == len(manifest["chunks"]) and not failures,
        "quality_note": (
            "Counts describe schema-valid model output and deterministic quote grounding; "
            "they are not a human-verified character-quality score. Overlap may duplicate mentions."
        ),
    }


def run_m1_document(
    *,
    document_text: str,
    provider: M1Provider,
    output_dir: Path,
    chunk_size: int = 8000,
    overlap_characters: int = 500,
    source_document_version_id: str | None = None,
    traces: Sequence[DeepSeekCallTrace] | None = None,
    progress: ProgressSink | None = None,
) -> dict[str, object]:
    """Run M1 over a raw document with resumable, per-chunk evidence artifacts."""
    if not document_text:
        raise ContractValidationError("document_text must be non-empty")
    document_hash = sha256_text(document_text)
    source_version = source_document_version_id or f"source-{document_hash[:16]}"
    policy = f"fixed-codepoint-window-{chunk_size}-overlap-{overlap_characters}-v1"
    manifest_object = build_document_chunk_manifest(
        document_text,
        source_document_version_id=source_version,
        chunk_size=chunk_size,
        overlap_characters=overlap_characters,
        chunking_policy_version=policy,
    )
    manifest = manifest_object.to_dict()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists() and _read_json(manifest_path) != manifest:
        raise ContractValidationError("existing output manifest does not match this run")
    _write_json(manifest_path, manifest)

    started_at = _utc_now()
    started_clock = time.monotonic()
    initial_trace_count = len(traces) if traces is not None else 0
    orchestrator = M1Orchestrator(provider)
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    resumed_chunks = 0
    chunks_dir = output_dir / "chunks"

    for index, entry in enumerate(manifest_object.chunks, start=1):
        result_path = chunks_dir / f"{entry.chunk_id}.json"
        if result_path.exists():
            existing = _read_json(result_path)
            if not isinstance(existing, dict):
                raise ContractValidationError(f"invalid saved chunk result: {entry.chunk_id}")
            if existing.get("schema_version") != M1_CHUNK_RESULT_VERSION:
                raise ContractValidationError(
                    f"saved chunk result schema mismatch: {entry.chunk_id}; use a new output directory"
                )
            if existing.get("chunk_id") != entry.chunk_id or existing.get("chunk_hash") != entry.chunk_hash:
                raise ContractValidationError(f"saved chunk result identity mismatch: {entry.chunk_id}")
            records.append(existing)
            resumed_chunks += 1
            if progress is not None:
                progress(f"[{index}/{len(manifest_object.chunks)}] resumed {entry.chunk_id}")
            continue

        envelope = M1OrchestrationEnvelope.from_manifest_entry(
            source_document_version_id=manifest_object.source_document_version_id,
            chunking_policy_version=manifest_object.chunking_policy_version,
            entry=entry,
            document_text=document_text,
        )
        trace_count = len(traces) if traces is not None else 0
        try:
            bound = orchestrator.run(envelope)
            grounded = ground_m1_result(bound)
            record: dict[str, object] = {
                "schema_version": M1_CHUNK_RESULT_VERSION,
                "chunk_index": index,
                "chunk_id": entry.chunk_id,
                "chunk_hash": entry.chunk_hash,
                "chunk_source_span": entry.chunk_source_span.to_dict(),
                "model_output": bound.model_output.to_dict(),
                "grounded_packet": grounded.to_packet_dict(),
                "grounding_trace_events": [event.to_dict() for event in grounded.trace_events],
                "provider_trace": _latest_trace(traces, trace_count),
            }
            _write_json(result_path, record)
            records.append(record)
            if progress is not None:
                progress(f"[{index}/{len(manifest_object.chunks)}] completed {entry.chunk_id}")
        except (ProviderError, ContractValidationError) as exc:
            failure: dict[str, object] = {
                "chunk_index": index,
                "chunk_id": entry.chunk_id,
                "chunk_hash": entry.chunk_hash,
                "error_type": type(exc).__name__,
                "message": str(exc),
                "provider_trace": _latest_trace(traces, trace_count),
            }
            failures.append(failure)
            if progress is not None:
                progress(
                    f"[{index}/{len(manifest_object.chunks)}] failed {entry.chunk_id}: "
                    f"{type(exc).__name__}: {exc}"
                )

    records.sort(key=lambda item: int(item["chunk_index"]))
    failures.sort(key=lambda item: int(item["chunk_index"]))
    model_outputs = [
        {
            "chunk_index": record["chunk_index"],
            "chunk_id": record["chunk_id"],
            "chunk_source_span": record["chunk_source_span"],
            "model_output": record["model_output"],
        }
        for record in records
    ]
    grounded_packets = [record["grounded_packet"] for record in records]
    grounding_traces = [
        {
            "chunk_index": record["chunk_index"],
            "chunk_id": record["chunk_id"],
            "trace_events": record["grounding_trace_events"],
        }
        for record in records
    ]
    _write_json(output_dir / "m1-model-outputs.json", model_outputs)
    _write_json(output_dir / "m1-grounded-packets.json", grounded_packets)
    _write_json(output_dir / "n2-grounding-traces.json", grounding_traces)
    _write_json(output_dir / "failures.json", failures)
    summary = _build_summary(
        started_at=started_at,
        duration_ms=max(0, round((time.monotonic() - started_clock) * 1000)),
        manifest=manifest,
        records=records,
        failures=failures,
        resumed_chunks=resumed_chunks,
        new_provider_calls=(len(traces) - initial_trace_count) if traces is not None else 0,
    )
    _write_json(output_dir / "summary.json", summary)
    return summary
