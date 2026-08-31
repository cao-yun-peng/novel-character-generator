from __future__ import annotations

import copy
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .errors import ContractValidationError, ProviderError
from .grounding import GroundingResult
from .m2 import (
    M2_PROMOTION_RESPONSE_SCHEMA,
    M2_PROMOTION_SYSTEM_INSTRUCTION,
    LocalCharacterRef,
    M2GroundedAttributionResult,
    M2GroundedFact,
    M2GroundingIssue,
    M2PromotionEnvelope,
    M2PromotionModelOutput,
    M2Provider,
    M2ProviderRequest,
    ground_m2_promotion_output,
)
from .m2_batch import _load_model_outputs, _parse_source_manifest, _replay_n2
from .n3 import N3ChunkResolutionResult, resolve_n3_chunk
from .providers import DeepSeekCallTrace
from .text import SourceSpan, sha256_text

N3_PROMOTION_SUMMARY_VERSION = "n3-promotion-batch-summary-v2"
N3_PROMOTION_TASK_VERSION = "n3-promotion-task-result-v2"
N3_PROMOTION_REPLAY_VERSION = "n3-promotion-source-replay-v1"

ProgressSink = Callable[[str], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"cannot read valid JSON from {path}") from exc


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{label} must be a non-empty string")
    return value


def _span(value: object, label: str) -> SourceSpan:
    item = _mapping(value, label)
    start, end = item.get("start"), item.get("end")
    if isinstance(start, bool) or not isinstance(start, int) or isinstance(end, bool) or not isinstance(end, int):
        raise ContractValidationError(f"{label} must contain integer start/end")
    return SourceSpan(start, end)


def _parse_m2_fact(value: object, label: str) -> M2GroundedFact:
    item = _mapping(value, label)
    return M2GroundedFact(
        fact_quote=_string(item.get("fact_quote"), f"{label}.fact_quote"),
        category=_string(item.get("category"), f"{label}.category"),
        attribute=_string(item.get("attribute"), f"{label}.attribute"),
        value=_string(item.get("value"), f"{label}.value"),
        source_mention_id=_string(item.get("source_mention_id"), f"{label}.source_mention_id"),
        source_mention_type=_string(item.get("source_mention_type"), f"{label}.source_mention_type"),
        source_evidence_quote=_string(item.get("source_evidence_quote"), f"{label}.source_evidence_quote"),
        source_evidence_span=_span(item.get("source_evidence_span"), f"{label}.source_evidence_span"),
        fact_chunk_span=_span(item.get("fact_chunk_span"), f"{label}.fact_chunk_span"),
        match_mode=_string(item.get("match_mode"), f"{label}.match_mode"),
    )


def _load_m2_results(source_m2_run_dir: Path) -> dict[str, tuple[M2GroundedAttributionResult, ...]]:
    raw = _read_json(source_m2_run_dir / "m2-grounded-results.json")
    if not isinstance(raw, list):
        raise ContractValidationError("m2-grounded-results.json must be an array")
    by_chunk: dict[str, list[M2GroundedAttributionResult]] = {}
    seen: set[tuple[str, str]] = set()
    for index, record_value in enumerate(raw):
        record = _mapping(record_value, f"M2 grounded record[{index}]")
        chunk_id = _string(record.get("chunk_id"), f"M2 grounded record[{index}].chunk_id")
        target_id = _string(
            record.get("target_local_mention_id"),
            f"M2 grounded record[{index}].target_local_mention_id",
        )
        if (chunk_id, target_id) in seen:
            raise ContractValidationError(f"duplicate M2 grounded result for {chunk_id}/{target_id}")
        seen.add((chunk_id, target_id))
        grounded = _mapping(record.get("grounded_result"), f"M2 grounded record[{index}].grounded_result")
        ref = _mapping(grounded.get("target_character_ref"), "target_character_ref")
        result = M2GroundedAttributionResult(
            target_character_ref=LocalCharacterRef(
                source_document_version_id=_string(ref.get("source_document_version_id"), "source_document_version_id"),
                chunk_id=_string(ref.get("chunk_id"), "target chunk_id"),
                local_mention_id=_string(ref.get("local_mention_id"), "local_mention_id"),
                packet_hash=_string(ref.get("packet_hash"), "packet_hash"),
                mention_type=_string(ref.get("mention_type"), "mention_type"),
            ),
            task_cache_key=_string(grounded.get("task_cache_key"), "task_cache_key"),
            grounded_belongs_to_target=tuple(
                _parse_m2_fact(fact, f"grounded_belongs_to_target[{fact_index}]")
                for fact_index, fact in enumerate(grounded.get("grounded_belongs_to_target", []))
            ),
            issues=tuple(
                M2GroundingIssue(
                    code=_string(_mapping(issue, "grounding issue").get("code"), "issue.code"),
                    fact_index=_mapping(issue, "grounding issue").get("fact_index"),
                    detail=_string(_mapping(issue, "grounding issue").get("detail"), "issue.detail"),
                )
                for issue in record.get("grounding_issues", [])
            ),
        )
        if result.target_character_ref.chunk_id != chunk_id or result.target_character_ref.local_mention_id != target_id:
            raise ContractValidationError("M2 record wrapper does not match target_character_ref")
        by_chunk.setdefault(chunk_id, []).append(result)
    return {chunk_id: tuple(results) for chunk_id, results in by_chunk.items()}


def _trace_dict(traces: Sequence[DeepSeekCallTrace] | None, before: int) -> dict[str, object] | None:
    if traces is None or len(traces) <= before:
        return None
    return traces[-1].to_dict()


def _append_history(output_dir: Path, summary: Mapping[str, object]) -> None:
    path = output_dir / "run-history.json"
    value = _read_json(path) if path.exists() else []
    if not isinstance(value, list):
        raise ContractValidationError("run-history.json must be an array")
    value.append(
        {
            key: summary[key]
            for key in (
                "started_at",
                "completed_at",
                "duration_ms",
                "planned_promotion_tasks",
                "succeeded_promotion_tasks",
                "failed_promotion_tasks",
                "resumed_promotion_tasks",
                "new_provider_calls",
                "complete",
            )
        }
    )
    _write_json(path, value)


def run_n3_promotion_from_m2_run(
    *,
    document_text: str,
    source_m1_run_dir: Path,
    source_m2_run_dir: Path,
    provider: M2Provider,
    output_dir: Path,
    traces: Sequence[DeepSeekCallTrace] | None = None,
    progress: ProgressSink | None = None,
) -> dict[str, object]:
    """Replay N2, resolve deterministic N3, then run resumable describe promotion."""
    if not document_text:
        raise ContractValidationError("document_text must be non-empty")
    manifest = _parse_source_manifest(_read_json(source_m1_run_dir / "manifest.json"), document_text)
    if manifest.document_hash != sha256_text(document_text):
        raise ContractValidationError("source document hash mismatch")
    n2_results, _ = _replay_n2(
        document_text=document_text,
        manifest=manifest,
        model_outputs=_load_model_outputs(source_m1_run_dir),
    )
    m2_results = _load_m2_results(source_m2_run_dir)
    source_m2_summary = _mapping(_read_json(source_m2_run_dir / "summary.json"), "source M2 summary")
    if source_m2_summary.get("complete") is not True:
        raise ContractValidationError("source M2 run must be complete")

    output_dir.mkdir(parents=True, exist_ok=True)
    replay = {
        "schema_version": N3_PROMOTION_REPLAY_VERSION,
        "source_m1_run_dir": str(source_m1_run_dir.resolve()),
        "source_m2_run_dir": str(source_m2_run_dir.resolve()),
        "document_hash": manifest.document_hash,
        "source_m1_manifest_hash": sha256_text((source_m1_run_dir / "manifest.json").read_text("utf-8")),
        "source_m2_grounded_results_hash": sha256_text((source_m2_run_dir / "m2-grounded-results.json").read_text("utf-8")),
    }
    replay_path = output_dir / "source-replay-manifest.json"
    if replay_path.exists() and _read_json(replay_path) != replay:
        raise ContractValidationError("existing N3/promotion output sources do not match")
    _write_json(replay_path, replay)

    entries = {entry.chunk_id: entry for entry in manifest.chunks}
    n3_chunks: list[N3ChunkResolutionResult] = []
    envelopes: list[tuple[int, GroundingResult, M2PromotionEnvelope]] = []
    for chunk_index, grounding in enumerate(n2_results, start=1):
        chunk_text = entries[grounding.chunk_id].chunk_source_span.quote(document_text)
        result = resolve_n3_chunk(
            grounding,
            m2_results.get(grounding.chunk_id, ()),
            chunk_text=chunk_text,
        )
        n3_chunks.append(result)
        for pool in result.describe_pool_results:
            if pool.next_action != "promote_remaining_describe":
                continue
            envelope = M2PromotionEnvelope.from_grounded_describe(
                grounding,
                chunk_text=chunk_text,
                describe_local_mention_id=pool.describe_source_ref.local_mention_id,
                remaining_fragments=pool.remaining_evidence_fragments,
                pool_hash_override=pool.pool_hash,
                resolver_version=pool.resolver_version,
            )
            envelopes.append((chunk_index, grounding, envelope))

    _write_json(output_dir / "n3-chunk-results.json", [item.to_dict() for item in n3_chunks])
    _write_json(
        output_dir / "n3-target-appearance-packets.json",
        [packet.to_dict() for result in n3_chunks for packet in result.target_appearance_packets],
    )
    _write_json(
        output_dir / "n3-describe-pool-results.json",
        [pool.to_dict() for result in n3_chunks for pool in result.describe_pool_results],
    )
    _write_json(output_dir / "promotion-envelopes.json", [item[2].to_dict() for item in envelopes])

    started_at = _utc_now()
    started_clock = time.monotonic()
    initial_traces = len(traces) if traces is not None else 0
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    resumed = 0
    for task_index, (chunk_index, grounding, envelope) in enumerate(envelopes, start=1):
        source_id = envelope.describe_source_ref.local_mention_id
        task_path = output_dir / "tasks" / f"{grounding.chunk_id}--{source_id}--{envelope.promotion_hash[:12]}.json"
        if task_path.exists():
            record = _mapping(_read_json(task_path), "saved promotion task")
            if record.get("schema_version") != N3_PROMOTION_TASK_VERSION or record.get("promotion_hash") != envelope.promotion_hash:
                raise ContractValidationError("saved promotion task does not match current envelope")
            records.append(dict(record))
            resumed += 1
            if progress:
                progress(f"[{task_index}/{len(envelopes)}] resumed {grounding.chunk_id}/{source_id}")
            continue
        trace_before = len(traces) if traces is not None else 0
        try:
            request = M2ProviderRequest(
                system_instruction=M2_PROMOTION_SYSTEM_INSTRUCTION,
                user_payload=copy.deepcopy(envelope.model_payload()),
                response_schema=copy.deepcopy(M2_PROMOTION_RESPONSE_SCHEMA),
                response_schema_name="m2_promote_remaining_describe",
            )
            model_output = M2PromotionModelOutput.parse(provider.generate(request))
            grounded = ground_m2_promotion_output(envelope, model_output)
            record = {
                "schema_version": N3_PROMOTION_TASK_VERSION,
                "chunk_index": chunk_index,
                "chunk_id": grounding.chunk_id,
                "describe_local_mention_id": source_id,
                "mention_quote": envelope.model_input.mention_quote,
                "promotion_hash": envelope.promotion_hash,
                "model_output": {
                    "characters": [
                        {
                            "character_label_quote": character.character_label_quote,
                            "belongs_to_character": [fact.to_dict() for fact in character.belongs_to_character],
                        }
                        for character in model_output.characters
                    ]
                },
                "grounded_result": grounded.to_packet_dict(),
                "grounding_issues": [issue.to_dict() for issue in grounded.issues],
                "provider_trace": _trace_dict(traces, trace_before),
            }
            _write_json(task_path, record)
            records.append(record)
            if progress:
                progress(f"[{task_index}/{len(envelopes)}] completed {grounding.chunk_id}/{source_id}")
        except (ProviderError, ContractValidationError) as exc:
            failures.append(
                {
                    "task_index": task_index,
                    "chunk_index": chunk_index,
                    "chunk_id": grounding.chunk_id,
                    "describe_local_mention_id": source_id,
                    "mention_quote": envelope.model_input.mention_quote,
                    "promotion_hash": envelope.promotion_hash,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "provider_trace": _trace_dict(traces, trace_before),
                }
            )
            if progress:
                progress(f"[{task_index}/{len(envelopes)}] failed {grounding.chunk_id}/{source_id}: {exc}")

    records.sort(key=lambda item: (int(item["chunk_index"]), str(item["describe_local_mention_id"])))
    _write_json(
        output_dir / "promotion-model-outputs.json",
        [
            {key: record[key] for key in ("chunk_index", "chunk_id", "describe_local_mention_id", "mention_quote", "promotion_hash", "model_output")}
            for record in records
        ],
    )
    _write_json(
        output_dir / "promotion-grounded-results.json",
        [
            {key: record[key] for key in ("chunk_index", "chunk_id", "describe_local_mention_id", "mention_quote", "grounded_result", "grounding_issues")}
            for record in records
        ],
    )
    _write_json(output_dir / "provider-traces.json", [record["provider_trace"] for record in records if record.get("provider_trace")])
    _write_json(output_dir / "failures.json", failures)

    target_packets = [packet for result in n3_chunks for packet in result.target_appearance_packets]
    pools = [pool for result in n3_chunks for pool in result.describe_pool_results]
    grounded_characters = [character for record in records for character in _mapping(record["grounded_result"], "grounded result").get("promoted_characters", [])]
    grounded_facts = [fact for character in grounded_characters for fact in _mapping(character, "promoted character").get("grounded_belongs_to_character", [])]
    issue_codes: dict[str, int] = {}
    for record in records:
        for issue in record.get("grounding_issues", []):
            code = str(_mapping(issue, "grounding issue").get("code"))
            issue_codes[code] = issue_codes.get(code, 0) + 1
    trace_values = [record["provider_trace"] for record in records if isinstance(record.get("provider_trace"), Mapping)]
    usage = {key: 0 for key in ("input_tokens", "input_cache_hit_tokens", "output_tokens", "reasoning_tokens", "total_tokens")}
    for trace in trace_values:
        trace_usage = _mapping(trace.get("usage", {}), "trace usage")
        for key in usage:
            value = trace_usage.get(key, 0)
            if isinstance(value, int):
                usage[key] += value
    summary = {
        "schema_version": N3_PROMOTION_SUMMARY_VERSION,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "duration_ms": max(0, round((time.monotonic() - started_clock) * 1000)),
        "document_hash": manifest.document_hash,
        "chunks": len(n3_chunks),
        "exact_target_packets": len(target_packets),
        "exact_target_facts": sum(len(packet.grounded_appearance_facts) for packet in target_packets),
        "describe_pools": len(pools),
        "consumed_describe_facts": sum(len(pool.consumed_fragments) for pool in pools),
        "conflicted_describe_facts": sum(len(pool.conflicted_fragments) for pool in pools),
        "remaining_evidence_fragments": sum(len(pool.remaining_evidence_fragments) for pool in pools),
        "collective_promotion_tasks": 0,
        "planned_promotion_tasks": len(envelopes),
        "succeeded_promotion_tasks": len(records),
        "failed_promotion_tasks": len(failures),
        "resumed_promotion_tasks": resumed,
        "new_provider_calls": (len(traces) - initial_traces) if traces is not None else 0,
        "recorded_provider_calls": len(trace_values),
        "promoted_characters": len(grounded_characters),
        "promoted_grounded_facts": len(grounded_facts),
        "promotion_grounding_issues": sum(issue_codes.values()),
        "promotion_grounding_issues_by_code": issue_codes,
        "promotion_review_required_tasks": sum(bool(record.get("grounding_issues")) for record in records),
        "review_required": bool(issue_codes or failures),
        "usage": usage,
        "complete": len(records) == len(envelopes) and not failures,
        "quality_note": "Complete means deterministic N3 and grounded promotion execution succeeded; it is not a human quality score.",
    }
    _write_json(output_dir / "summary.json", summary)
    _append_history(output_dir, summary)
    return summary
