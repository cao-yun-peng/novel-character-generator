from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .appearance_transition import (
    AppearanceTransitionProvider,
    build_appearance_transition_chunks,
    build_transition_request,
    deduplicate_grounded_transitions,
    ground_transition_events,
    materialize_appearance_states,
    parse_transition_model_output,
    transition_chunks_artifact,
)
from .errors import ContractValidationError, ProviderError

TRANSITION_CHUNK_RESULT_VERSION = "appearance-transition-chunk-result-v1"
TRANSITION_BATCH_SUMMARY_VERSION = "appearance-transition-batch-summary-v1"
ProgressSink = Callable[[str], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _load_sources(
    *,
    profiles_file: Path,
    local_nodes_file: Path,
    fact_groups_file: Path,
    scopes_file: Path,
) -> tuple[Mapping[str, object], Mapping[str, object], Mapping[str, object], Mapping[str, object]]:
    return (
        _mapping(_read_json(profiles_file), "profiles"),
        _mapping(_read_json(local_nodes_file), "local nodes"),
        _mapping(_read_json(fact_groups_file), "fact groups"),
        _mapping(_read_json(scopes_file), "appearance scopes"),
    )


def prepare_document_appearance_transitions(
    *,
    document_text: str,
    profiles_file: Path,
    local_nodes_file: Path,
    scopes_file: Path,
    chunk_manifest_file: Path,
    output_dir: Path,
) -> dict[str, object]:
    profiles = _mapping(_read_json(profiles_file), "profiles")
    local_nodes = _mapping(_read_json(local_nodes_file), "local nodes")
    scopes = _mapping(_read_json(scopes_file), "appearance scopes")
    chunk_manifest = _mapping(_read_json(chunk_manifest_file), "source Chunk manifest")
    source_version, source_policy, windows = build_appearance_transition_chunks(
        document_text=document_text,
        profiles=profiles,
        local_nodes=local_nodes,
        scopes=scopes,
        chunk_manifest=chunk_manifest,
    )
    artifact = transition_chunks_artifact(
        source_document_version_id=source_version,
        windows=windows,
        total_characters=len(document_text),
        source_chunking_policy_version=source_policy,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "transition-chunks.json"
    if path.exists() and _read_json(path) != artifact:
        raise ContractValidationError("existing transition windows do not match current sources/config")
    _write_json(path, artifact)
    summary = dict(_mapping(artifact["summary"], "transition window summary"))
    _write_json(output_dir / "summary.json", summary)
    _write_json(output_dir / "failures.json", [])
    _write_json(output_dir / "review.json", [])
    return summary


def _latest_trace(traces: Sequence[object] | None, previous_count: int) -> dict[str, object] | None:
    if traces is None or len(traces) <= previous_count:
        return None
    to_dict = getattr(traces[-1], "to_dict", None)
    if not callable(to_dict):
        raise ContractValidationError("transition Provider trace must support to_dict()")
    value = to_dict()
    return dict(_mapping(value, "transition Provider trace"))


def run_document_appearance_transitions(
    *,
    document_text: str,
    profiles_file: Path,
    local_nodes_file: Path,
    fact_groups_file: Path,
    scopes_file: Path,
    chunk_manifest_file: Path,
    output_dir: Path,
    provider: AppearanceTransitionProvider,
    traces: Sequence[object] | None = None,
    progress: ProgressSink | None = None,
) -> dict[str, object]:
    profiles, local_nodes, fact_groups, scopes = _load_sources(
        profiles_file=profiles_file,
        local_nodes_file=local_nodes_file,
        fact_groups_file=fact_groups_file,
        scopes_file=scopes_file,
    )
    chunk_manifest = _mapping(_read_json(chunk_manifest_file), "source Chunk manifest")
    source_version, source_policy, windows = build_appearance_transition_chunks(
        document_text=document_text,
        profiles=profiles,
        local_nodes=local_nodes,
        scopes=scopes,
        chunk_manifest=chunk_manifest,
    )
    expected_windows = transition_chunks_artifact(
        source_document_version_id=source_version,
        windows=windows,
        total_characters=len(document_text),
        source_chunking_policy_version=source_policy,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    windows_path = output_dir / "transition-chunks.json"
    if windows_path.exists() and _read_json(windows_path) != expected_windows:
        raise ContractValidationError("saved transition windows do not match current sources/config")
    _write_json(windows_path, expected_windows)

    started_at = _utc_now()
    started_clock = time.monotonic()
    initial_trace_count = len(traces) if traces is not None else 0
    trace_path = output_dir / "provider-traces.json"
    saved_traces = _read_json(trace_path) if trace_path.exists() else []
    if not isinstance(saved_traces, list) or any(not isinstance(item, Mapping) for item in saved_traces):
        raise ContractValidationError("transition provider-traces.json must be an array of objects")
    current_call_traces: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    resumed = 0
    new_calls = 0

    for window in windows:
        result_path = output_dir / "chunks" / f"{window.chunk_id}.json"
        expected_names = [character.name for character in window.characters]
        expected_identity = {
            "chunk_id": window.chunk_id,
            "chunk_hash": window.chunk_hash,
            "document_span": window.document_span.to_dict(),
            "characters": [character.model_dict() for character in window.characters],
        }
        if result_path.exists():
            existing = _mapping(_read_json(result_path), "saved transition window result")
            if existing.get("schema_version") != TRANSITION_CHUNK_RESULT_VERSION:
                raise ContractValidationError("saved transition window result version mismatch")
            if existing.get("identity") != expected_identity:
                raise ContractValidationError("saved transition window result identity mismatch")
            model_output = _mapping(existing.get("model_output"), "saved transition model output")
            events = parse_transition_model_output(
                model_output,
                allowed_characters=expected_names,
            )
            grounded, review = ground_transition_events(window, events)
            refreshed = dict(existing)
            refreshed["grounded_transitions"] = [dict(item) for item in grounded]
            refreshed["review"] = [dict(item) for item in review]
            _write_json(result_path, refreshed)
            results.append(refreshed)
            resumed += 1
            if progress is not None:
                progress(f"[{window.number}/{len(windows)}] resumed")
            continue

        if not window.characters:
            record = {
                "schema_version": TRANSITION_CHUNK_RESULT_VERSION,
                "identity": expected_identity,
                "model_output": {"events": []},
                "grounded_transitions": [],
                "review": [],
                "provider_trace": None,
            }
            _write_json(result_path, record)
            results.append(record)
            if progress is not None:
                progress(f"[{window.number}/{len(windows)}] no identified characters")
            continue

        previous_trace_count = len(traces) if traces is not None else 0
        try:
            request = build_transition_request(window)
            new_calls += 1
            raw_output = provider.generate(request)
            events = parse_transition_model_output(raw_output, allowed_characters=expected_names)
            grounded, review = ground_transition_events(window, events)
            provider_trace = _latest_trace(traces, previous_trace_count)
            if provider_trace is not None:
                current_call_traces.append(provider_trace)
            record = {
                "schema_version": TRANSITION_CHUNK_RESULT_VERSION,
                "identity": expected_identity,
                "model_output": {"events": [dict(event) for event in events]},
                "grounded_transitions": [dict(item) for item in grounded],
                "review": [dict(item) for item in review],
                "provider_trace": provider_trace,
            }
            _write_json(result_path, record)
            results.append(record)
            if progress is not None:
                progress(f"[{window.number}/{len(windows)}] completed")
        except (ProviderError, ContractValidationError) as exc:
            provider_trace = _latest_trace(traces, previous_trace_count)
            if provider_trace is not None:
                current_call_traces.append(provider_trace)
            failures.append(
                {
                    "chunk_id": window.chunk_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "provider_trace": provider_trace,
                }
            )
            if progress is not None:
                progress(f"[{window.number}/{len(windows)}] failed: {exc}")

    all_grounded = [
        item
        for result in results
        for item in result.get("grounded_transitions", [])
        if isinstance(item, Mapping)
    ]
    review = [
        dict(item)
        for result in results
        for item in result.get("review", [])
        if isinstance(item, Mapping)
    ]
    transitions = deduplicate_grounded_transitions(all_grounded)
    complete = len(results) == len(windows) and not failures
    if complete:
        states = materialize_appearance_states(
            document_text=document_text,
            source_document_version_id=source_version,
            scopes=scopes,
            fact_groups=fact_groups,
            transitions=transitions,
            review=review,
            planned_chunks=len(windows),
            model_calls=sum(bool(window.characters) for window in windows),
        )
        _write_json(output_dir / "document-character-appearance-states.json", states)

    trace_items = [dict(item) for item in saved_traces] + current_call_traces
    summary = {
        "schema_version": TRANSITION_BATCH_SUMMARY_VERSION,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "duration_ms": int((time.monotonic() - started_clock) * 1000),
        "planned_chunks": len(windows),
        "succeeded_chunks": len(results),
        "failed_chunks": len(failures),
        "resumed_chunks": resumed,
        "new_provider_calls": new_calls,
        "grounded_transitions": len(transitions),
        "review_items": len(review),
        "complete": complete,
    }
    _write_json(output_dir / "failures.json", failures)
    _write_json(output_dir / "review.json", review)
    _write_json(trace_path, trace_items)
    _write_json(output_dir / "summary.json", summary)
    history_path = output_dir / "run-history.json"
    history = _read_json(history_path) if history_path.exists() else []
    if not isinstance(history, list):
        raise ContractValidationError("transition run-history.json must be an array")
    history.append(summary)
    _write_json(history_path, history)

    if traces is not None and len(traces) - initial_trace_count < new_calls:
        raise ContractValidationError("transition Provider trace count is smaller than calls")
    return summary
