from __future__ import annotations

import copy
import json
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .errors import ContractValidationError, ProviderError
from .identity import (
    IDENTITY_CANDIDATE_POLICY_VERSION,
    IDENTITY_CONTEXT_POLICY_VERSION,
    IDENTITY_LOCAL_COREFERENCE_POLICY_VERSION,
    IDENTITY_POLICY_VERSION,
    M3_IDENTITY_RESPONSE_SCHEMA,
    M3_IDENTITY_SYSTEM_INSTRUCTION,
    GroundedIdentityDecision,
    IdentityModelOutput,
    IdentityPreparation,
    IdentityProvider,
    IdentityProviderRequest,
    build_document_character_registry,
    build_document_local_character_nodes,
    build_identity_preparation,
    ground_identity_model_output,
)

IDENTITY_PREPARATION_MANIFEST_VERSION = "identity-preparation-manifest-v1"
IDENTITY_PREPARATION_SUMMARY_VERSION = "identity-preparation-summary-v1"
IDENTITY_BATCH_SUMMARY_VERSION = "identity-batch-summary-v1"
IDENTITY_TASK_RESULT_VERSION = "identity-task-result-v1"

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


def _file_hash(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ContractValidationError(f"cannot hash identity source artifact {path}") from exc


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _load_preparation(
    *,
    document_text: str,
    source_n2_packets_file: Path,
    source_n3_run_dir: Path,
    document_evidence_file: Path,
    max_candidates_per_node: int,
    context_radius: int,
    max_contexts_per_node: int,
    max_bridge_characters: int,
    max_local_coreference_characters: int,
) -> tuple[IdentityPreparation, dict[str, object]]:
    target_path = source_n3_run_dir / "n3-target-appearance-packets.json"
    promotion_path = source_n3_run_dir / "promotion-grounded-results.json"
    source_n2 = _sequence(_read_json(source_n2_packets_file), "source N2 grounded packets")
    n3_targets = _sequence(_read_json(target_path), "N3 target packets")
    promotions = _sequence(_read_json(promotion_path), "promotion grounded results")
    document_evidence = _mapping(_read_json(document_evidence_file), "document character evidence")
    local_nodes = build_document_local_character_nodes(
        document_text=document_text,
        source_n2_packets=source_n2,
        n3_target_packets=n3_targets,
        promotion_grounded_results=promotions,
        document_evidence=document_evidence,
        context_radius=context_radius,
        max_contexts_per_node=max_contexts_per_node,
    )
    preparation = build_identity_preparation(
        local_nodes=local_nodes,
        document_text=document_text,
        max_candidates_per_node=max_candidates_per_node,
        max_bridge_characters=max_bridge_characters,
        max_local_coreference_characters=max_local_coreference_characters,
    )
    source_artifacts = {
        "source_n2_grounded_packets": {
            "path": str(source_n2_packets_file.resolve()),
            "hash": _file_hash(source_n2_packets_file),
        },
        "n3_target_appearance_packets": {
            "path": str(target_path.resolve()),
            "hash": _file_hash(target_path),
        },
        "promotion_grounded_results": {
            "path": str(promotion_path.resolve()),
            "hash": _file_hash(promotion_path),
        },
        "document_character_evidence": {
            "path": str(document_evidence_file.resolve()),
            "hash": _file_hash(document_evidence_file),
        },
    }
    manifest = {
        "schema_version": IDENTITY_PREPARATION_MANIFEST_VERSION,
        "source_document_version_id": local_nodes.source_document_version_id,
        "document_hash": local_nodes.document_hash,
        "source_artifacts": source_artifacts,
        "configuration": {
            "max_candidates_per_node": max_candidates_per_node,
            "context_radius": context_radius,
            "max_contexts_per_node": max_contexts_per_node,
            "max_bridge_characters": max_bridge_characters,
            "max_local_coreference_characters": max_local_coreference_characters,
        },
        "contracts": {
            "identity_policy_version": IDENTITY_POLICY_VERSION,
            "candidate_policy_version": IDENTITY_CANDIDATE_POLICY_VERSION,
            "context_policy_version": IDENTITY_CONTEXT_POLICY_VERSION,
            "local_coreference_policy_version": IDENTITY_LOCAL_COREFERENCE_POLICY_VERSION,
            "system_instruction_hash": _canonical_hash(M3_IDENTITY_SYSTEM_INSTRUCTION),
            "response_schema_hash": _canonical_hash(M3_IDENTITY_RESPONSE_SCHEMA),
        },
    }
    return preparation, manifest


def _write_preparation_artifacts(
    output_dir: Path,
    preparation: IdentityPreparation,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "identity-preparation-manifest.json"
    if manifest_path.exists() and _read_json(manifest_path) != manifest:
        raise ContractValidationError("existing identity output sources or configuration do not match")
    _write_json(manifest_path, manifest)
    _write_json(output_dir / "document-local-character-nodes.json", preparation.local_nodes.to_dict())
    _write_json(output_dir / "identity-deterministic-edges.json", list(preparation.deterministic_edges))
    _write_json(output_dir / "identity-envelopes.json", [item.to_dict() for item in preparation.envelopes])
    reason_counts: dict[str, int] = {}
    deterministic_reason_counts: dict[str, int] = {}
    tasks_per_node: dict[str, int] = {}
    for envelope in preparation.envelopes:
        tasks_per_node[envelope.current_node_key] = tasks_per_node.get(envelope.current_node_key, 0) + 1
        for reason in envelope.candidate_reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    for edge in preparation.deterministic_edges:
        reason = str(edge.get("reason"))
        deterministic_reason_counts[reason] = deterministic_reason_counts.get(reason, 0) + 1
    summary = preparation.summary()
    summary.update(
        {
            "schema_version": IDENTITY_PREPARATION_SUMMARY_VERSION,
            "candidate_reasons": dict(sorted(reason_counts.items())),
            "deterministic_edge_reasons": dict(sorted(deterministic_reason_counts.items())),
            "max_tasks_for_one_node": max(tasks_per_node.values(), default=0),
            "model_outputs": 0,
            "grounded_identity_decisions": 0,
            "registry_built": False,
            "review_required": bool(preparation.envelopes),
        }
    )
    return summary


def prepare_document_identity(
    *,
    document_text: str,
    source_n2_packets_file: Path,
    source_n3_run_dir: Path,
    document_evidence_file: Path,
    output_dir: Path,
    max_candidates_per_node: int = 2,
    context_radius: int = 240,
    max_contexts_per_node: int = 4,
    max_bridge_characters: int = 1200,
    max_local_coreference_characters: int = 600,
) -> dict[str, object]:
    """Build identity nodes and bounded M3 tasks without calling a Provider."""
    preparation, manifest = _load_preparation(
        document_text=document_text,
        source_n2_packets_file=source_n2_packets_file,
        source_n3_run_dir=source_n3_run_dir,
        document_evidence_file=document_evidence_file,
        max_candidates_per_node=max_candidates_per_node,
        context_radius=context_radius,
        max_contexts_per_node=max_contexts_per_node,
        max_bridge_characters=max_bridge_characters,
        max_local_coreference_characters=max_local_coreference_characters,
    )
    summary = _write_preparation_artifacts(output_dir, preparation, manifest)
    _write_json(output_dir / "identity-model-outputs.json", [])
    _write_json(output_dir / "grounded-identity-decisions.json", [])
    _write_json(output_dir / "provider-traces.json", [])
    _write_json(output_dir / "failures.json", [])
    _write_json(output_dir / "summary.json", summary)
    return summary


def _latest_trace(traces: Sequence[object] | None, previous_count: int) -> dict[str, object] | None:
    if traces is None or len(traces) <= previous_count:
        return None
    trace = traces[-1]
    to_dict = getattr(trace, "to_dict", None)
    if not callable(to_dict):
        raise ContractValidationError("identity Provider trace must support to_dict()")
    value = to_dict()
    return dict(_mapping(value, "identity Provider trace"))


def _append_run_history(output_dir: Path, summary: Mapping[str, object]) -> None:
    path = output_dir / "run-history.json"
    value = _read_json(path) if path.exists() else []
    if not isinstance(value, list):
        raise ContractValidationError("identity run-history.json must be an array")
    value.append(
        {
            key: summary[key]
            for key in (
                "started_at",
                "completed_at",
                "duration_ms",
                "planned_tasks",
                "succeeded_tasks",
                "failed_tasks",
                "resumed_tasks",
                "new_provider_calls",
                "complete",
                "registry_built",
            )
        }
    )
    _write_json(path, value)


def run_document_identity(
    *,
    document_text: str,
    source_n2_packets_file: Path,
    source_n3_run_dir: Path,
    document_evidence_file: Path,
    provider: IdentityProvider,
    output_dir: Path,
    max_candidates_per_node: int = 2,
    context_radius: int = 240,
    max_contexts_per_node: int = 4,
    max_bridge_characters: int = 1200,
    max_local_coreference_characters: int = 600,
    traces: Sequence[object] | None = None,
    progress: ProgressSink | None = None,
) -> dict[str, object]:
    """Execute resumable M3 identity decisions and build the grounded document registry."""
    preparation, manifest = _load_preparation(
        document_text=document_text,
        source_n2_packets_file=source_n2_packets_file,
        source_n3_run_dir=source_n3_run_dir,
        document_evidence_file=document_evidence_file,
        max_candidates_per_node=max_candidates_per_node,
        context_radius=context_radius,
        max_contexts_per_node=max_contexts_per_node,
        max_bridge_characters=max_bridge_characters,
        max_local_coreference_characters=max_local_coreference_characters,
    )
    preparation_summary = _write_preparation_artifacts(output_dir, preparation, manifest)
    node_by_key = {node.node_key: node for node in preparation.local_nodes.nodes}
    started_at = _utc_now()
    started_clock = time.monotonic()
    initial_trace_count = len(traces) if traces is not None else 0
    records: list[dict[str, object]] = []
    decisions: list[GroundedIdentityDecision] = []
    failures: list[dict[str, object]] = []
    resumed_tasks = 0
    new_provider_calls = 0
    tasks_dir = output_dir / "tasks"

    for task_index, envelope in enumerate(preparation.envelopes, start=1):
        current = node_by_key[envelope.current_node_key]
        candidate = node_by_key[envelope.candidate_node_key]
        task_path = tasks_dir / (
            f"{envelope.current_node_key[:12]}--{envelope.candidate_node_key[:12]}--"
            f"{envelope.task_cache_key[:12]}.json"
        )
        trace_before = len(traces) if traces is not None else 0
        try:
            if task_path.exists():
                saved = _mapping(_read_json(task_path), "saved identity task result")
                if (
                    saved.get("schema_version") != IDENTITY_TASK_RESULT_VERSION
                    or saved.get("task_cache_key") != envelope.task_cache_key
                ):
                    raise ContractValidationError("saved identity task does not match current envelope")
                model_output = IdentityModelOutput.parse(
                    _mapping(saved.get("model_output"), "saved identity model_output")
                )
                provider_trace = saved.get("provider_trace")
                resumed_tasks += 1
                action = "resumed"
            else:
                request = IdentityProviderRequest(
                    system_instruction=M3_IDENTITY_SYSTEM_INSTRUCTION,
                    user_payload=copy.deepcopy(envelope.model_payload()),
                    response_schema=copy.deepcopy(M3_IDENTITY_RESPONSE_SCHEMA),
                    response_schema_name="m3_character_identity_relation",
                )
                new_provider_calls += 1
                model_output = IdentityModelOutput.parse(provider.generate(request))
                provider_trace = _latest_trace(traces, trace_before)
                action = "completed"
            grounded = ground_identity_model_output(
                envelope,
                model_output,
                document_text=document_text,
            )
            record = {
                "schema_version": IDENTITY_TASK_RESULT_VERSION,
                "task_index": task_index,
                "current_label_quote": current.label_quote,
                "candidate_label_quote": candidate.label_quote,
                "task_cache_key": envelope.task_cache_key,
                "model_output": model_output.to_dict(),
                "grounded_result": grounded.to_dict(),
                "provider_trace": provider_trace,
            }
            _write_json(task_path, record)
            records.append(record)
            decisions.append(grounded)
            if progress is not None:
                progress(
                    f"[{task_index}/{len(preparation.envelopes)}] {action} "
                    f"{current.label_quote} -> {candidate.label_quote}: {grounded.identity_relation}"
                )
        except (ProviderError, ContractValidationError) as exc:
            failures.append(
                {
                    "task_index": task_index,
                    "current_label_quote": current.label_quote,
                    "candidate_label_quote": candidate.label_quote,
                    "task_cache_key": envelope.task_cache_key,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "provider_trace": _latest_trace(traces, trace_before),
                }
            )
            if progress is not None:
                progress(
                    f"[{task_index}/{len(preparation.envelopes)}] failed "
                    f"{current.label_quote} -> {candidate.label_quote}: {type(exc).__name__}: {exc}"
                )

    records.sort(key=lambda item: int(item["task_index"]))
    decisions.sort(
        key=lambda item: (
            node_by_key[item.current_node_key].order_position,
            item.current_node_key,
            item.candidate_node_key,
        )
    )
    failures.sort(key=lambda item: int(item["task_index"]))
    _write_json(
        output_dir / "identity-model-outputs.json",
        [
            {
                "task_index": record["task_index"],
                "current_label_quote": record["current_label_quote"],
                "candidate_label_quote": record["candidate_label_quote"],
                "task_cache_key": record["task_cache_key"],
                "model_output": record["model_output"],
            }
            for record in records
        ],
    )
    _write_json(
        output_dir / "grounded-identity-decisions.json",
        [decision.to_dict() for decision in decisions],
    )
    _write_json(
        output_dir / "provider-traces.json",
        [record["provider_trace"] for record in records if record.get("provider_trace") is not None],
    )
    _write_json(output_dir / "failures.json", failures)

    complete = len(records) == len(preparation.envelopes) and not failures
    registry: dict[str, object] | None = None
    if complete:
        registry = build_document_character_registry(
            preparation=preparation,
            grounded_decisions=decisions,
        )
        _write_json(output_dir / "document-character-registry.json", registry)
    relation_counts = {relation: 0 for relation in ("same_character", "different_characters", "uncertain")}
    issue_counts: dict[str, int] = {}
    for decision in decisions:
        relation_counts[decision.identity_relation] += 1
        for issue in decision.issues:
            issue_counts[issue.code] = issue_counts.get(issue.code, 0) + 1
    summary = {
        **preparation_summary,
        "schema_version": IDENTITY_BATCH_SUMMARY_VERSION,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "duration_ms": max(0, round((time.monotonic() - started_clock) * 1000)),
        "planned_tasks": len(preparation.envelopes),
        "succeeded_tasks": len(records),
        "failed_tasks": len(failures),
        "resumed_tasks": resumed_tasks,
        "new_provider_calls": new_provider_calls,
        "recorded_provider_calls": len(traces) - initial_trace_count if traces is not None else 0,
        "identity_relations": relation_counts,
        "grounding_issues": sum(issue_counts.values()),
        "grounding_issues_by_code": dict(sorted(issue_counts.items())),
        "model_outputs": len(records),
        "grounded_identity_decisions": len(decisions),
        "registry_built": registry is not None,
        "registry_summary": registry["summary"] if registry is not None else None,
        "review_required": bool(registry and registry["review_items"]),
        "complete": complete,
        "quality_note": (
            "Completion proves bounded structured execution and strict quote grounding; "
            "identity precision still requires human review or a labeled evaluation set."
        ),
    }
    _write_json(output_dir / "summary.json", summary)
    _append_run_history(output_dir, summary)
    return summary
