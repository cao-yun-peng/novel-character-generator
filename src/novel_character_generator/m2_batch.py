from __future__ import annotations

import copy
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .chunking import ChunkManifestEntry, DocumentChunkManifest
from .errors import ContractValidationError, ProviderError
from .grounding import GroundingResult, ground_m1_result
from .m1 import M1BoundMention, M1BoundResult, M1ModelOutput, M1OrchestrationEnvelope
from .m2 import (
    M2_ATTRIBUTION_RESPONSE_SCHEMA,
    M2_ATTRIBUTION_SYSTEM_INSTRUCTION,
    M2AttributionModelOutput,
    M2Provider,
    M2ProviderRequest,
    build_m2_attribution_envelopes,
    ground_m2_attribution_output,
)
from .providers import DeepSeekCallTrace
from .text import SourceSpan, sha256_text

M2_BATCH_SUMMARY_VERSION = "m2-batch-summary-v1"
M2_TASK_RESULT_VERSION = "m2-attribution-task-result-v1"
M2_REPLAY_MANIFEST_VERSION = "m2-source-replay-manifest-v1"

ProgressSink = Callable[[str], None]


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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"cannot read valid JSON from {path}") from exc


def _expect_mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _expect_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{label} must be a non-empty string")
    return value


def _expect_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractValidationError(f"{label} must be an integer")
    return value


def _parse_span(value: object, *, label: str) -> SourceSpan:
    mapping = _expect_mapping(value, label=label)
    if set(mapping) != {"start", "end"}:
        raise ContractValidationError(f"{label} fields mismatch")
    return SourceSpan(
        _expect_int(mapping["start"], label=f"{label}.start"),
        _expect_int(mapping["end"], label=f"{label}.end"),
    )


def _parse_source_manifest(value: object, document_text: str) -> DocumentChunkManifest:
    mapping = _expect_mapping(value, label="source manifest")
    chunks_value = mapping.get("chunks")
    if not isinstance(chunks_value, list) or not chunks_value:
        raise ContractValidationError("source manifest chunks must be a non-empty array")
    chunks: list[ChunkManifestEntry] = []
    for index, item in enumerate(chunks_value):
        chunk = _expect_mapping(item, label=f"source manifest chunks[{index}]")
        chunks.append(
            ChunkManifestEntry(
                chunk_id=_expect_string(chunk.get("chunk_id"), label="chunk_id"),
                chunk_hash=_expect_string(chunk.get("chunk_hash"), label="chunk_hash"),
                chunk_source_span=_parse_span(chunk.get("chunk_source_span"), label="chunk_source_span"),
                overlap_left_characters=_expect_int(
                    chunk.get("overlap_left_characters"), label="overlap_left_characters"
                ),
                overlap_right_characters=_expect_int(
                    chunk.get("overlap_right_characters"), label="overlap_right_characters"
                ),
            )
        )
    manifest = DocumentChunkManifest(
        source_document_version_id=_expect_string(
            mapping.get("source_document_version_id"), label="source_document_version_id"
        ),
        document_hash=_expect_string(mapping.get("document_hash"), label="document_hash"),
        chunking_policy_version=_expect_string(
            mapping.get("chunking_policy_version"), label="chunking_policy_version"
        ),
        total_characters=_expect_int(mapping.get("total_characters"), label="total_characters"),
        coverage_status=_expect_string(mapping.get("coverage_status"), label="coverage_status"),
        truncation_reason=(
            mapping.get("truncation_reason")
            if mapping.get("truncation_reason") is None
            or isinstance(mapping.get("truncation_reason"), str)
            else "__invalid__"
        ),
        processed_source_end=_expect_int(
            mapping.get("processed_source_end"), label="processed_source_end"
        ),
        chunks=tuple(chunks),
        schema_version=_expect_string(mapping.get("schema_version"), label="schema_version"),
    )
    manifest.validate(document_text)
    return manifest


def _load_model_outputs(source_run_dir: Path) -> dict[str, M1ModelOutput]:
    value = _read_json(source_run_dir / "m1-model-outputs.json")
    if not isinstance(value, list):
        raise ContractValidationError("m1-model-outputs.json must be an array")
    outputs: dict[str, M1ModelOutput] = {}
    for index, item in enumerate(value):
        record = _expect_mapping(item, label=f"M1 output[{index}]")
        chunk_id = _expect_string(record.get("chunk_id"), label=f"M1 output[{index}].chunk_id")
        if chunk_id in outputs:
            raise ContractValidationError(f"duplicate M1 model output for {chunk_id}")
        outputs[chunk_id] = M1ModelOutput.parse(
            _expect_mapping(record.get("model_output"), label=f"M1 output[{index}].model_output")
        )
    return outputs


def _replay_n2(
    *,
    document_text: str,
    manifest: DocumentChunkManifest,
    model_outputs: Mapping[str, M1ModelOutput],
) -> tuple[tuple[GroundingResult, ...], tuple[dict[str, object], ...]]:
    expected_ids = {entry.chunk_id for entry in manifest.chunks}
    if set(model_outputs) != expected_ids:
        raise ContractValidationError(
            "M1 model output chunk set does not match source manifest; "
            f"missing={sorted(expected_ids - set(model_outputs))}, "
            f"extra={sorted(set(model_outputs) - expected_ids)}"
        )
    results: list[GroundingResult] = []
    traces: list[dict[str, object]] = []
    for index, entry in enumerate(manifest.chunks, start=1):
        envelope = M1OrchestrationEnvelope.from_manifest_entry(
            source_document_version_id=manifest.source_document_version_id,
            chunking_policy_version=manifest.chunking_policy_version,
            entry=entry,
            document_text=document_text,
        )
        output = model_outputs[entry.chunk_id]
        bound = M1BoundResult(
            envelope=envelope,
            model_output=output,
            mentions=tuple(
                M1BoundMention(local_mention_id=f"m{mention_index}", candidate=candidate)
                for mention_index, candidate in enumerate(output.candidate_mentions, start=1)
            ),
        )
        grounded = ground_m1_result(bound)
        results.append(grounded)
        traces.append(
            {
                "chunk_index": index,
                "chunk_id": entry.chunk_id,
                "trace_events": [event.to_dict() for event in grounded.trace_events],
            }
        )
    return tuple(results), tuple(traces)


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
    manifest: DocumentChunkManifest,
    n2_results: Sequence[GroundingResult],
    records: list[dict[str, object]],
    failures: list[dict[str, object]],
    planned_tasks: int,
    resumed_tasks: int,
    new_provider_calls: int,
) -> dict[str, object]:
    exact_mentions = sum(
        mention.mention_type == "exact"
        for result in n2_results
        for mention in result.single_character_mentions
    )
    describe_mentions = sum(
        mention.mention_type == "describe"
        for result in n2_results
        for mention in result.single_character_mentions
    )
    collective_mentions = sum(len(result.quarantined_collective_mentions) for result in n2_results)
    n2_bindings = sum(
        len(mention.approved_evidence)
        for result in n2_results
        for mention in result.grounded_mentions
    )
    model_facts = sum(
        len(record.get("model_output", {}).get("belongs_to_target", []))
        for record in records
        if isinstance(record.get("model_output"), dict)
    )
    grounded_facts = [
        fact
        for record in records
        if isinstance(record.get("grounded_result"), dict)
        for fact in record["grounded_result"].get("grounded_belongs_to_target", [])
        if isinstance(fact, dict)
    ]
    issues = [
        issue
        for record in records
        for issue in record.get("grounding_issues", [])
        if isinstance(issue, dict)
    ]
    trace_dicts = [
        trace for record in records if isinstance((trace := record.get("provider_trace")), dict)
    ]
    usages = [
        usage for trace in trace_dicts if isinstance((usage := trace.get("usage")), dict)
    ]
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
    issue_counts: dict[str, int] = {}
    for issue in issues:
        code = str(issue.get("code"))
        issue_counts[code] = issue_counts.get(code, 0) + 1
    source_counts = {"exact": 0, "describe": 0}
    for fact in grounded_facts:
        source_type = fact.get("source_mention_type")
        if source_type in source_counts:
            source_counts[str(source_type)] += 1
    return {
        "schema_version": M2_BATCH_SUMMARY_VERSION,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "duration_ms": duration_ms,
        "source_run_schema": _expect_mapping(
            _read_json(Path(records[0]["source_run_dir"]) / "summary.json"),
            label="source summary",
        ).get("schema_version") if records else None,
        "source_document_version_id": manifest.source_document_version_id,
        "document_hash": manifest.document_hash,
        "chunking_policy_version": manifest.chunking_policy_version,
        "chunks": len(manifest.chunks),
        "n2_replay": {
            "exact_mentions": exact_mentions,
            "individual_describe_mentions": describe_mentions,
            "collective_mentions": collective_mentions,
            "approved_evidence_bindings": n2_bindings,
        },
        "planned_tasks": planned_tasks,
        "succeeded_tasks": len(records),
        "failed_tasks": len(failures),
        "resumed_tasks": resumed_tasks,
        "new_provider_calls": new_provider_calls,
        "recorded_provider_calls": len(trace_dicts),
        "models": sorted(
            {
                str(trace["model"])
                for trace in trace_dicts
                if isinstance(trace.get("model"), str)
            }
        ),
        "model_facts": model_facts,
        "grounded_facts": len(grounded_facts),
        "grounded_facts_by_source_type": source_counts,
        "grounding_issues": len(issues),
        "grounding_issues_by_code": issue_counts,
        "usage": usage,
        "usage_scope": "all_succeeded_task_records",
        "complete": len(records) == planned_tasks and not failures,
        "quality_note": (
            "A complete run proves structured execution and deterministic grounding only; "
            "it is not a human-verified M2 attribution quality score. Promotion requires N3 remaining pools."
        ),
    }


def _append_run_history(output_dir: Path, summary: Mapping[str, object]) -> None:
    history_path = output_dir / "run-history.json"
    if history_path.exists():
        value = _read_json(history_path)
        if not isinstance(value, list):
            raise ContractValidationError("run-history.json must be an array")
        history = list(value)
    else:
        history = []
    started_at = summary.get("started_at")
    if not any(isinstance(item, Mapping) and item.get("started_at") == started_at for item in history):
        history.append(
            {
                "started_at": started_at,
                "completed_at": summary.get("completed_at"),
                "duration_ms": summary.get("duration_ms"),
                "planned_tasks": summary.get("planned_tasks"),
                "succeeded_tasks": summary.get("succeeded_tasks"),
                "failed_tasks": summary.get("failed_tasks"),
                "resumed_tasks": summary.get("resumed_tasks"),
                "new_provider_calls": summary.get("new_provider_calls"),
                "recorded_provider_calls": summary.get("recorded_provider_calls"),
                "complete": summary.get("complete"),
            }
        )
    _write_json(history_path, history)


def run_m2_from_m1_run(
    *,
    document_text: str,
    source_run_dir: Path,
    provider: M2Provider,
    output_dir: Path,
    traces: Sequence[DeepSeekCallTrace] | None = None,
    progress: ProgressSink | None = None,
) -> dict[str, object]:
    """Replay current N2 from a saved M1 run, then run resumable M2 attribution."""
    if not document_text:
        raise ContractValidationError("document_text must be non-empty")
    manifest = _parse_source_manifest(
        _read_json(source_run_dir / "manifest.json"),
        document_text,
    )
    if manifest.document_hash != sha256_text(document_text):
        raise ContractValidationError("source document hash mismatch")
    model_outputs = _load_model_outputs(source_run_dir)
    n2_results, n2_traces = _replay_n2(
        document_text=document_text,
        manifest=manifest,
        model_outputs=model_outputs,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    replay_manifest = {
        "schema_version": M2_REPLAY_MANIFEST_VERSION,
        "source_run_dir": str(source_run_dir.resolve()),
        "source_manifest_hash": sha256_text(
            (source_run_dir / "manifest.json").read_text(encoding="utf-8")
        ),
        "source_model_outputs_hash": sha256_text(
            (source_run_dir / "m1-model-outputs.json").read_text(encoding="utf-8")
        ),
        "source_document_version_id": manifest.source_document_version_id,
        "document_hash": manifest.document_hash,
        "chunking_policy_version": manifest.chunking_policy_version,
    }
    replay_path = output_dir / "source-replay-manifest.json"
    if replay_path.exists() and _read_json(replay_path) != replay_manifest:
        raise ContractValidationError("existing M2 output source replay manifest does not match")
    _write_json(replay_path, replay_manifest)
    _write_json(
        output_dir / "source-n2-grounded-packets.json",
        [result.to_packet_dict() for result in n2_results],
    )
    _write_json(output_dir / "source-n2-grounding-traces.json", list(n2_traces))

    entries_by_id = {entry.chunk_id: entry for entry in manifest.chunks}
    planned: list[tuple[int, GroundingResult, object]] = []
    for chunk_index, grounding in enumerate(n2_results, start=1):
        entry = entries_by_id[grounding.chunk_id]
        chunk_text = entry.chunk_source_span.quote(document_text)
        for envelope in build_m2_attribution_envelopes(grounding, chunk_text=chunk_text):
            planned.append((chunk_index, grounding, envelope))

    started_at = _utc_now()
    started_clock = time.monotonic()
    initial_trace_count = len(traces) if traces is not None else 0
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    resumed_tasks = 0
    tasks_dir = output_dir / "tasks"

    for task_index, (chunk_index, grounding, envelope_value) in enumerate(planned, start=1):
        envelope = envelope_value
        target_id = envelope.target_character_ref.local_mention_id
        result_path = tasks_dir / (
            f"{grounding.chunk_id}--{target_id}--{envelope.task_cache_key[:12]}.json"
        )
        if result_path.exists():
            existing = _expect_mapping(_read_json(result_path), label="saved M2 task result")
            if existing.get("schema_version") != M2_TASK_RESULT_VERSION:
                raise ContractValidationError("saved M2 task result schema mismatch")
            if existing.get("task_cache_key") != envelope.task_cache_key:
                raise ContractValidationError("saved M2 task cache key mismatch")
            records.append(dict(existing))
            resumed_tasks += 1
            if progress is not None:
                progress(f"[{task_index}/{len(planned)}] resumed {grounding.chunk_id}/{target_id}")
            continue

        trace_count = len(traces) if traces is not None else 0
        try:
            request = M2ProviderRequest(
                system_instruction=M2_ATTRIBUTION_SYSTEM_INSTRUCTION,
                user_payload=copy.deepcopy(envelope.model_payload()),
                response_schema=copy.deepcopy(M2_ATTRIBUTION_RESPONSE_SCHEMA),
                response_schema_name="m2_target_appearance_facts",
            )
            model_output = M2AttributionModelOutput.parse(provider.generate(request))
            grounded_output = ground_m2_attribution_output(envelope, model_output)
            record: dict[str, object] = {
                "schema_version": M2_TASK_RESULT_VERSION,
                "source_run_dir": str(source_run_dir.resolve()),
                "chunk_index": chunk_index,
                "chunk_id": grounding.chunk_id,
                "target_local_mention_id": target_id,
                "target_mention_quote": envelope.model_input.target.mention_quote,
                "task_cache_key": envelope.task_cache_key,
                "model_output": model_output.to_dict(),
                "grounded_result": grounded_output.to_packet_dict(),
                "grounding_issues": [issue.to_dict() for issue in grounded_output.issues],
                "provider_trace": _latest_trace(traces, trace_count),
            }
            _write_json(result_path, record)
            records.append(record)
            if progress is not None:
                progress(f"[{task_index}/{len(planned)}] completed {grounding.chunk_id}/{target_id}")
        except (ProviderError, ContractValidationError) as exc:
            failures.append(
                {
                    "task_index": task_index,
                    "chunk_index": chunk_index,
                    "chunk_id": grounding.chunk_id,
                    "target_local_mention_id": target_id,
                    "target_mention_quote": envelope.model_input.target.mention_quote,
                    "task_cache_key": envelope.task_cache_key,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "provider_trace": _latest_trace(traces, trace_count),
                }
            )
            if progress is not None:
                progress(
                    f"[{task_index}/{len(planned)}] failed {grounding.chunk_id}/{target_id}: "
                    f"{type(exc).__name__}: {exc}"
                )

    records.sort(key=lambda item: (int(item["chunk_index"]), str(item["target_local_mention_id"])))
    failures.sort(key=lambda item: int(item["task_index"]))
    _write_json(
        output_dir / "m2-envelopes.json",
        [envelope.to_dict() for _, _, envelope in planned],
    )
    _write_json(
        output_dir / "m2-model-outputs.json",
        [
            {
                "chunk_index": record["chunk_index"],
                "chunk_id": record["chunk_id"],
                "target_local_mention_id": record["target_local_mention_id"],
                "target_mention_quote": record["target_mention_quote"],
                "task_cache_key": record["task_cache_key"],
                "model_output": record["model_output"],
            }
            for record in records
        ],
    )
    _write_json(
        output_dir / "m2-grounded-results.json",
        [
            {
                "chunk_index": record["chunk_index"],
                "chunk_id": record["chunk_id"],
                "target_local_mention_id": record["target_local_mention_id"],
                "target_mention_quote": record["target_mention_quote"],
                "grounded_result": record["grounded_result"],
                "grounding_issues": record["grounding_issues"],
            }
            for record in records
        ],
    )
    _write_json(
        output_dir / "provider-traces.json",
        [record["provider_trace"] for record in records if record.get("provider_trace") is not None],
    )
    _write_json(output_dir / "failures.json", failures)
    summary = _build_summary(
        started_at=started_at,
        duration_ms=max(0, round((time.monotonic() - started_clock) * 1000)),
        manifest=manifest,
        n2_results=n2_results,
        records=records,
        failures=failures,
        planned_tasks=len(planned),
        resumed_tasks=resumed_tasks,
        new_provider_calls=(len(traces) - initial_trace_count) if traces is not None else 0,
    )
    _write_json(output_dir / "summary.json", summary)
    _append_run_history(output_dir, summary)
    return summary
