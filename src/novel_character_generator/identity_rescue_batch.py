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
    GroundedIdentityDecision,
    GroundedIdentityEvidence,
    IdentityAppearanceFactRef,
    IdentityCandidateModelInput,
    IdentityContextBinding,
    IdentityCurrentModelInput,
    IdentityEnvelope,
    IdentityGroundingIssue,
    IdentityModelInput,
    IdentityPreparation,
    IdentityProvider,
    IdentityProviderRequest,
    DocumentLocalCharacterNodes,
    LocalCharacterNode,
    build_document_character_registry,
)
from .identity_rescue import (
    CLUSTER_RESCUE_POLICY_VERSION,
    CLUSTER_RESCUE_SYSTEM_INSTRUCTION,
    CLUSTER_RELATION_CONTEXT_VERSION,
    ClusterRescueModelOutput,
    GroundedClusterRescueDecision,
    build_cluster_rescue_preparation,
    cluster_rescue_response_schema,
    ground_cluster_rescue_output,
)
from .text import SourceSpan, sha256_text

CLUSTER_RESCUE_MANIFEST_VERSION = "cluster-rescue-manifest-v1"
CLUSTER_RESCUE_TASK_RESULT_VERSION = "cluster-rescue-task-result-v1"
CLUSTER_RESCUE_BATCH_SUMMARY_VERSION = "cluster-rescue-batch-summary-v1"

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


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractValidationError(f"{label} must be an integer")
    return value


def _span(value: object, label: str) -> SourceSpan:
    item = _mapping(value, label)
    return SourceSpan(_integer(item.get("start"), f"{label}.start"), _integer(item.get("end"), f"{label}.end"))


def _file_hash(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ContractValidationError(f"cannot hash cluster rescue source artifact {path}") from exc


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _parse_local_nodes(raw: object) -> DocumentLocalCharacterNodes:
    value = _mapping(raw, "document local character nodes")
    nodes: list[LocalCharacterNode] = []
    for index, raw_node in enumerate(_sequence(value.get("nodes"), "local nodes")):
        node = _mapping(raw_node, f"local nodes[{index}]")
        contexts = tuple(
            IdentityContextBinding(
                _string(item.get("context_quote"), "context_quote"),
                _span(item.get("document_span"), "context document_span"),
                _string(item.get("source_kind"), "context source_kind"),
            )
            for raw_context in _sequence(node.get("context_bindings"), "context_bindings")
            for item in [_mapping(raw_context, "context_binding")]
        )
        facts = tuple(
            IdentityAppearanceFactRef(
                _string(item.get("fact_hash"), "fact_hash"),
                _string(item.get("fact_quote"), "fact_quote"),
                _string(item.get("category"), "category"),
                _string(item.get("attribute"), "attribute"),
                _string(item.get("value"), "value"),
                _span(item.get("document_fact_span"), "document_fact_span"),
            )
            for raw_fact in _sequence(node.get("appearance_fact_refs"), "appearance_fact_refs")
            for item in [_mapping(raw_fact, "appearance_fact_ref")]
        )
        nodes.append(
            LocalCharacterNode(
                _string(node.get("node_key"), "node_key"),
                _string(node.get("ref_type"), "ref_type"),
                _mapping(node.get("source_character_ref"), "source_character_ref"),
                _string(node.get("character_origin"), "character_origin"),
                _string(node.get("label_quote"), "label_quote"),
                _string(node.get("label_type"), "label_type"),
                _string(node.get("chunk_id"), "chunk_id"),
                _span(node.get("chunk_source_span"), "chunk_source_span"),
                contexts,
                facts,
                _integer(node.get("order_position"), "order_position"),
            )
        )
    return DocumentLocalCharacterNodes(
        _string(value.get("source_document_version_id"), "source_document_version_id"),
        _string(value.get("document_hash"), "document_hash"),
        tuple(nodes),
        _string(value.get("context_policy_version"), "context_policy_version"),
        _string(value.get("schema_version"), "schema_version"),
    )


def _parse_envelopes(
    raw: object,
    *,
    context_policy_version: str,
) -> tuple[IdentityEnvelope, ...]:
    envelopes: list[IdentityEnvelope] = []
    for index, raw_envelope in enumerate(_sequence(raw, "identity envelopes")):
        envelope = _mapping(raw_envelope, f"identity envelopes[{index}]")
        raw_input = _mapping(envelope.get("model_input"), "identity model_input")
        current = _mapping(raw_input.get("current_character"), "current_character")
        candidate = _mapping(raw_input.get("candidate_character"), "candidate_character")
        model_input = IdentityModelInput(
            IdentityCurrentModelInput(
                _string(current.get("label_quote"), "current label_quote"),
                _string(current.get("label_type"), "current label_type"),
                tuple(_string(item, "current context_quote") for item in _sequence(current.get("context_quotes"), "current context_quotes")),
                tuple(_string(item, "current fact_quote") for item in _sequence(current.get("appearance_fact_quotes"), "current appearance facts")),
            ),
            IdentityCandidateModelInput(
                tuple(_string(item, "candidate known_label") for item in _sequence(candidate.get("known_labels"), "candidate known_labels")),
                tuple(_string(item, "candidate context_quote") for item in _sequence(candidate.get("context_quotes"), "candidate context_quotes")),
                tuple(_string(item, "candidate fact_quote") for item in _sequence(candidate.get("appearance_fact_quotes"), "candidate appearance facts")),
            ),
            tuple(_string(item, "bridge context_quote") for item in _sequence(raw_input.get("bridge_context_quotes"), "bridge_context_quotes")),
        )
        bindings = tuple(
            IdentityContextBinding(
                _string(item.get("context_quote"), "identity context_quote"),
                _span(item.get("document_span"), "identity context span"),
                _string(item.get("source_kind"), "identity context source_kind"),
            )
            for raw_binding in _sequence(envelope.get("context_bindings"), "identity context_bindings")
            for item in [_mapping(raw_binding, "identity context_binding")]
        )
        envelopes.append(
            IdentityEnvelope(
                _string(envelope.get("current_node_key"), "current_node_key"),
                _string(envelope.get("candidate_node_key"), "candidate_node_key"),
                tuple(_string(item, "candidate_reason") for item in _sequence(envelope.get("candidate_reasons"), "candidate_reasons")),
                bindings,
                _string(envelope.get("task_cache_key"), "task_cache_key"),
                model_input,
                _string(envelope.get("schema_version"), "identity envelope schema_version"),
                context_policy_version,
            )
        )
    return tuple(envelopes)


def _parse_decisions(raw: object) -> tuple[GroundedIdentityDecision, ...]:
    decisions: list[GroundedIdentityDecision] = []
    for index, raw_decision in enumerate(_sequence(raw, "grounded identity decisions")):
        decision = _mapping(raw_decision, f"grounded identity decisions[{index}]")
        evidence = tuple(
            GroundedIdentityEvidence(
                _string(item.get("evidence_quote"), "identity evidence_quote"),
                _span(item.get("document_span"), "identity evidence span"),
                _string(item.get("match_mode"), "identity evidence match_mode"),
            )
            for raw_evidence in _sequence(decision.get("grounded_identity_evidence"), "grounded_identity_evidence")
            for item in [_mapping(raw_evidence, "grounded identity evidence")]
        )
        issues = tuple(
            IdentityGroundingIssue(
                _string(item.get("code"), "identity issue code"),
                item.get("evidence_index") if isinstance(item.get("evidence_index"), int) else None,
                item.get("evidence_quote") if isinstance(item.get("evidence_quote"), str) else None,
                item.get("candidate_occurrence_count") if isinstance(item.get("candidate_occurrence_count"), int) else None,
                _string(item.get("detail"), "identity issue detail"),
            )
            for raw_issue in _sequence(decision.get("issues"), "identity issues")
            for item in [_mapping(raw_issue, "identity issue")]
        )
        decisions.append(
            GroundedIdentityDecision(
                _string(decision.get("current_node_key"), "current_node_key"),
                _string(decision.get("candidate_node_key"), "candidate_node_key"),
                _string(decision.get("task_cache_key"), "task_cache_key"),
                _string(decision.get("requested_identity_relation"), "requested_identity_relation"),
                _string(decision.get("identity_relation"), "identity_relation"),
                decision.get("label_relation") if isinstance(decision.get("label_relation"), str) else None,
                evidence,
                issues,
                _string(decision.get("schema_version"), "grounded decision schema_version"),
            )
        )
    return tuple(decisions)


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _optional_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _integer(value, label)


def _parse_cluster_rescue_decisions(
    raw: object,
    *,
    document_text: str,
) -> tuple[GroundedClusterRescueDecision, ...]:
    decisions: list[GroundedClusterRescueDecision] = []
    for index, raw_decision in enumerate(_sequence(raw, "grounded cluster rescue decisions")):
        decision = _mapping(raw_decision, f"grounded cluster rescue decisions[{index}]")
        evidence = tuple(
            GroundedIdentityEvidence(
                _string(item.get("evidence_quote"), "cluster rescue evidence_quote"),
                _span(item.get("document_span"), "cluster rescue evidence span"),
                _string(item.get("match_mode"), "cluster rescue evidence match_mode"),
            )
            for raw_evidence in _sequence(
                decision.get("grounded_identity_evidence"),
                "cluster rescue grounded_identity_evidence",
            )
            for item in [_mapping(raw_evidence, "cluster rescue grounded identity evidence")]
        )
        issues = tuple(
            IdentityGroundingIssue(
                _string(item.get("code"), "cluster rescue issue code"),
                item.get("evidence_index") if isinstance(item.get("evidence_index"), int) else None,
                item.get("evidence_quote") if isinstance(item.get("evidence_quote"), str) else None,
                item.get("candidate_occurrence_count")
                if isinstance(item.get("candidate_occurrence_count"), int)
                else None,
                _string(item.get("detail"), "cluster rescue issue detail"),
            )
            for raw_issue in _sequence(decision.get("issues"), "cluster rescue issues")
            for item in [_mapping(raw_issue, "cluster rescue issue")]
        )
        parsed = GroundedClusterRescueDecision(
            _string(decision.get("subject_character_id"), "subject_character_id"),
            _string(decision.get("subject_anchor_node_key"), "subject_anchor_node_key"),
            _optional_integer(decision.get("selected_candidate_number"), "selected_candidate_number"),
            _optional_string(decision.get("selected_candidate_character_id"), "selected_candidate_character_id"),
            _optional_string(
                decision.get("selected_candidate_anchor_node_key"),
                "selected_candidate_anchor_node_key",
            ),
            _string(decision.get("task_cache_key"), "cluster rescue task_cache_key"),
            _string(decision.get("requested_identity_relation"), "requested_identity_relation"),
            _string(decision.get("identity_relation"), "identity_relation"),
            _optional_string(decision.get("label_relation"), "label_relation"),
            evidence,
            issues,
            _string(decision.get("schema_version"), "cluster rescue decision schema_version"),
        )
        if parsed.identity_relation not in {"same_character", "different_characters", "uncertain"}:
            raise ContractValidationError("seed cluster rescue decision has invalid identity_relation")
        for grounded in parsed.grounded_identity_evidence:
            if grounded.document_span.quote(document_text) != grounded.evidence_quote:
                raise ContractValidationError("seed cluster rescue evidence no longer replays against document")
        decisions.append(parsed)
    return tuple(decisions)


def _load_seed_cluster_rescue_decisions(
    *,
    document_text: str,
    seed_rescue_run_dir: Path | None,
) -> tuple[tuple[GroundedClusterRescueDecision, ...], Mapping[str, object] | None]:
    if seed_rescue_run_dir is None:
        return (), None
    decisions_path = seed_rescue_run_dir / "grounded-cluster-rescue-decisions.json"
    decisions = _parse_cluster_rescue_decisions(
        _read_json(decisions_path),
        document_text=document_text,
    )
    return decisions, {
        "path": str(decisions_path.resolve()),
        "hash": _file_hash(decisions_path),
        "decision_count": len(decisions),
    }


def _supplemental_decisions(
    decisions: Sequence[GroundedClusterRescueDecision],
) -> tuple[GroundedIdentityDecision, ...]:
    return tuple(
        supplemental
        for decision in decisions
        for supplemental in [decision.to_supplemental_decision()]
        if supplemental is not None
    )


def load_saved_identity_run(
    *,
    document_text: str,
    source_identity_run_dir: Path,
) -> tuple[IdentityPreparation, tuple[GroundedIdentityDecision, ...], Mapping[str, object]]:
    manifest_path = source_identity_run_dir / "identity-preparation-manifest.json"
    nodes_path = source_identity_run_dir / "document-local-character-nodes.json"
    envelopes_path = source_identity_run_dir / "identity-envelopes.json"
    edges_path = source_identity_run_dir / "identity-deterministic-edges.json"
    decisions_path = source_identity_run_dir / "grounded-identity-decisions.json"
    manifest = _mapping(_read_json(manifest_path), "identity preparation manifest")
    document_hash = _string(manifest.get("document_hash"), "identity manifest document_hash")
    if sha256_text(document_text) != document_hash:
        raise ContractValidationError("cluster rescue source identity run belongs to another document")
    contracts = _mapping(manifest.get("contracts"), "identity manifest contracts")
    context_policy = _string(contracts.get("context_policy_version"), "context_policy_version")
    local_nodes = _parse_local_nodes(_read_json(nodes_path))
    if local_nodes.document_hash != document_hash:
        raise ContractValidationError("saved local nodes document hash mismatch")
    envelopes = _parse_envelopes(_read_json(envelopes_path), context_policy_version=context_policy)
    edges = tuple(_mapping(item, "deterministic edge") for item in _sequence(_read_json(edges_path), "deterministic edges"))
    decisions = _parse_decisions(_read_json(decisions_path))
    for envelope in envelopes:
        for binding in envelope.context_bindings:
            if binding.document_span.quote(document_text) != binding.context_quote:
                raise ContractValidationError("saved identity context no longer replays against document")
    for decision in decisions:
        for evidence in decision.grounded_identity_evidence:
            if evidence.document_span.quote(document_text) != evidence.evidence_quote:
                raise ContractValidationError("saved identity evidence no longer replays against document")
    preparation = IdentityPreparation(
        local_nodes,
        edges,
        envelopes,
        _string(contracts.get("candidate_policy_version"), "candidate_policy_version"),
    )
    source_artifacts = {
        "identity_preparation_manifest": {"path": str(manifest_path.resolve()), "hash": _file_hash(manifest_path)},
        "document_local_character_nodes": {"path": str(nodes_path.resolve()), "hash": _file_hash(nodes_path)},
        "identity_envelopes": {"path": str(envelopes_path.resolve()), "hash": _file_hash(envelopes_path)},
        "identity_deterministic_edges": {"path": str(edges_path.resolve()), "hash": _file_hash(edges_path)},
        "grounded_identity_decisions": {"path": str(decisions_path.resolve()), "hash": _file_hash(decisions_path)},
    }
    return preparation, decisions, source_artifacts


def _build_preparation(
    *,
    document_text: str,
    source_identity_run_dir: Path,
    max_candidates_per_task: int,
    max_contexts_per_character: int,
    max_relationship_contexts_per_candidate: int,
    max_relationship_context_characters: int,
):
    preparation, decisions, source_artifacts = load_saved_identity_run(
        document_text=document_text,
        source_identity_run_dir=source_identity_run_dir,
    )
    baseline = build_document_character_registry(
        preparation=preparation,
        grounded_decisions=decisions,
    )
    rescue = build_cluster_rescue_preparation(
        preparation=preparation,
        grounded_decisions=decisions,
        baseline_registry=baseline,
        document_text=document_text,
        max_candidates_per_task=max_candidates_per_task,
        max_contexts_per_character=max_contexts_per_character,
        max_relationship_contexts_per_candidate=max_relationship_contexts_per_candidate,
        max_relationship_context_characters=max_relationship_context_characters,
    )
    manifest = {
        "schema_version": CLUSTER_RESCUE_MANIFEST_VERSION,
        "source_document_version_id": preparation.local_nodes.source_document_version_id,
        "document_hash": preparation.local_nodes.document_hash,
        "source_artifacts": source_artifacts,
        "configuration": {
            "max_candidates_per_task": max_candidates_per_task,
            "max_contexts_per_character": max_contexts_per_character,
            "max_relationship_contexts_per_candidate": max_relationship_contexts_per_candidate,
            "max_relationship_context_characters": max_relationship_context_characters,
        },
        "contracts": {
            "policy_version": CLUSTER_RESCUE_POLICY_VERSION,
            "context_version": CLUSTER_RELATION_CONTEXT_VERSION,
            "system_instruction_hash": _canonical_hash(CLUSTER_RESCUE_SYSTEM_INSTRUCTION),
        },
    }
    return preparation, decisions, rescue, manifest


def _write_preparation(output_dir: Path, rescue, manifest: Mapping[str, object]) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "cluster-rescue-manifest.json"
    if manifest_path.exists() and _read_json(manifest_path) != manifest:
        raise ContractValidationError("existing cluster rescue output sources or configuration do not match")
    _write_json(manifest_path, manifest)
    _write_json(output_dir / "baseline-document-character-registry.json", rescue.baseline_registry)
    _write_json(output_dir / "cluster-rescue-envelopes.json", [item.to_dict() for item in rescue.envelopes])
    return rescue.summary()


def prepare_identity_rescue(
    *,
    document_text: str,
    source_identity_run_dir: Path,
    output_dir: Path,
    max_candidates_per_task: int = 3,
    max_contexts_per_character: int = 4,
    max_relationship_contexts_per_candidate: int = 3,
    max_relationship_context_characters: int = 1200,
) -> dict[str, object]:
    _, _, rescue, manifest = _build_preparation(
        document_text=document_text,
        source_identity_run_dir=source_identity_run_dir,
        max_candidates_per_task=max_candidates_per_task,
        max_contexts_per_character=max_contexts_per_character,
        max_relationship_contexts_per_candidate=max_relationship_contexts_per_candidate,
        max_relationship_context_characters=max_relationship_context_characters,
    )
    summary = _write_preparation(output_dir, rescue, manifest)
    summary.update({"complete": True, "registry_built": False})
    _write_json(output_dir / "cluster-rescue-model-outputs.json", [])
    _write_json(output_dir / "grounded-cluster-rescue-decisions.json", [])
    _write_json(output_dir / "provider-traces.json", [])
    _write_json(output_dir / "failures.json", [])
    _write_json(output_dir / "summary.json", summary)
    return summary


def _latest_trace(traces: Sequence[object] | None, previous_count: int) -> dict[str, object] | None:
    if traces is None or len(traces) <= previous_count:
        return None
    to_dict = getattr(traces[-1], "to_dict", None)
    if not callable(to_dict):
        raise ContractValidationError("cluster rescue Provider trace must support to_dict()")
    return dict(_mapping(to_dict(), "cluster rescue Provider trace"))


def _append_history(output_dir: Path, summary: Mapping[str, object]) -> None:
    path = output_dir / "run-history.json"
    history = _read_json(path) if path.exists() else []
    if not isinstance(history, list):
        raise ContractValidationError("cluster rescue run-history.json must be an array")
    history.append(
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
    _write_json(path, history)


def run_identity_rescue(
    *,
    document_text: str,
    source_identity_run_dir: Path,
    provider: IdentityProvider,
    output_dir: Path,
    max_candidates_per_task: int = 3,
    max_contexts_per_character: int = 4,
    max_relationship_contexts_per_candidate: int = 3,
    max_relationship_context_characters: int = 1200,
    seed_rescue_run_dir: Path | None = None,
    max_rounds: int = 3,
    max_new_provider_calls: int = 10,
    traces: Sequence[object] | None = None,
    progress: ProgressSink | None = None,
) -> dict[str, object]:
    if max_rounds < 1:
        raise ContractValidationError("cluster rescue max_rounds must be positive")
    if max_new_provider_calls < 0:
        raise ContractValidationError("cluster rescue max_new_provider_calls cannot be negative")
    preparation, base_decisions, rescue, manifest = _build_preparation(
        document_text=document_text,
        source_identity_run_dir=source_identity_run_dir,
        max_candidates_per_task=max_candidates_per_task,
        max_contexts_per_character=max_contexts_per_character,
        max_relationship_contexts_per_candidate=max_relationship_contexts_per_candidate,
        max_relationship_context_characters=max_relationship_context_characters,
    )
    seeded_grounded, seed_artifact = _load_seed_cluster_rescue_decisions(
        document_text=document_text,
        seed_rescue_run_dir=seed_rescue_run_dir,
    )
    accumulated_supplemental = list(_supplemental_decisions(seeded_grounded))
    current_registry = build_document_character_registry(
        preparation=preparation,
        grounded_decisions=base_decisions,
        supplemental_grounded_decisions=tuple(accumulated_supplemental),
    )
    if seeded_grounded:
        rescue = build_cluster_rescue_preparation(
            preparation=preparation,
            grounded_decisions=base_decisions,
            baseline_registry=current_registry,
            document_text=document_text,
            max_candidates_per_task=max_candidates_per_task,
            max_contexts_per_character=max_contexts_per_character,
            max_relationship_contexts_per_candidate=max_relationship_contexts_per_candidate,
            max_relationship_context_characters=max_relationship_context_characters,
        )
    initial_registry_summary = current_registry.get("summary")
    manifest = copy.deepcopy(dict(manifest))
    configuration = dict(_mapping(manifest.get("configuration"), "cluster rescue configuration"))
    configuration.update(
        {
            "max_rounds": max_rounds,
            "max_new_provider_calls": max_new_provider_calls,
        }
    )
    manifest["configuration"] = configuration
    if seed_artifact is not None:
        source_artifacts = dict(_mapping(manifest.get("source_artifacts"), "cluster rescue source_artifacts"))
        source_artifacts["seed_grounded_cluster_rescue_decisions"] = dict(seed_artifact)
        manifest["source_artifacts"] = source_artifacts
    preparation_summary = _write_preparation(output_dir, rescue, manifest)
    _write_json(
        output_dir / "seed-grounded-cluster-rescue-decisions.json",
        [item.to_dict() for item in seeded_grounded],
    )
    started_at = _utc_now()
    started_clock = time.monotonic()
    initial_trace_count = len(traces) if traces is not None else 0
    records: list[dict[str, object]] = []
    new_grounded_decisions: list[GroundedClusterRescueDecision] = []
    failures: list[dict[str, object]] = []
    round_summaries: list[dict[str, object]] = []
    round_envelopes: list[dict[str, object]] = []
    resumed_tasks = 0
    new_provider_calls = 0
    tasks_dir = output_dir / "tasks"
    fixed_point_reached = False
    termination_reason = "max_rounds"
    total_planned_tasks = 0
    for round_index in range(1, max_rounds + 1):
        if not rescue.envelopes:
            fixed_point_reached = True
            termination_reason = "no_pending_tasks"
            break
        registry_before_hash = _canonical_hash(current_registry)
        round_records: list[dict[str, object]] = []
        round_decisions: list[GroundedClusterRescueDecision] = []
        round_failure_count_before = len(failures)
        round_new_calls_before = new_provider_calls
        total_planned_tasks += len(rescue.envelopes)
        for envelope in rescue.envelopes:
            global_task_index = len(records) + len(failures) + 1
            round_envelopes.append(
                {
                    "round_index": round_index,
                    "task_index": global_task_index,
                    "envelope": envelope.to_dict(),
                }
            )
            task_path = tasks_dir / f"{envelope.subject_anchor_node_key[:12]}--{envelope.task_cache_key[:12]}.json"
            trace_before = len(traces) if traces is not None else 0
            try:
                if task_path.exists():
                    saved = _mapping(_read_json(task_path), "saved cluster rescue task")
                    if (
                        saved.get("schema_version") != CLUSTER_RESCUE_TASK_RESULT_VERSION
                        or saved.get("task_cache_key") != envelope.task_cache_key
                    ):
                        raise ContractValidationError("saved cluster rescue task does not match current envelope")
                    model_output = ClusterRescueModelOutput.parse(
                        _mapping(saved.get("model_output"), "saved cluster rescue model_output"),
                        candidate_count=len(envelope.candidate_bindings),
                    )
                    provider_trace = saved.get("provider_trace")
                    resumed_tasks += 1
                    action = "resumed"
                else:
                    if new_provider_calls >= max_new_provider_calls:
                        raise ContractValidationError("cluster rescue max_new_provider_calls reached")
                    request = IdentityProviderRequest(
                        system_instruction=CLUSTER_RESCUE_SYSTEM_INSTRUCTION,
                        user_payload=copy.deepcopy(envelope.model_payload()),
                        response_schema=cluster_rescue_response_schema(len(envelope.candidate_bindings)),
                        response_schema_name="m3_cluster_identity_rescue",
                    )
                    new_provider_calls += 1
                    model_output = ClusterRescueModelOutput.parse(
                        provider.generate(request),
                        candidate_count=len(envelope.candidate_bindings),
                    )
                    provider_trace = _latest_trace(traces, trace_before)
                    action = "completed"
                grounded = ground_cluster_rescue_output(
                    envelope,
                    model_output,
                    document_text=document_text,
                )
                record = {
                    "schema_version": CLUSTER_RESCUE_TASK_RESULT_VERSION,
                    "round_index": round_index,
                    "task_index": global_task_index,
                    "task_cache_key": envelope.task_cache_key,
                    "subject_labels": list(envelope.model_input.current_character.labels),
                    "model_output": model_output.to_dict(),
                    "grounded_result": grounded.to_dict(),
                    "provider_trace": provider_trace,
                }
                _write_json(task_path, record)
                records.append(record)
                round_records.append(record)
                new_grounded_decisions.append(grounded)
                round_decisions.append(grounded)
                if progress is not None:
                    progress(
                        f"[round {round_index} task {len(round_records)}/{len(rescue.envelopes)}] {action} "
                        f"{'/'.join(envelope.model_input.current_character.labels)}: {grounded.identity_relation}"
                    )
            except (ProviderError, ContractValidationError) as exc:
                failures.append(
                    {
                        "round_index": round_index,
                        "task_index": global_task_index,
                        "task_cache_key": envelope.task_cache_key,
                        "subject_labels": list(envelope.model_input.current_character.labels),
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "provider_trace": _latest_trace(traces, trace_before),
                    }
                )
                if progress is not None:
                    progress(f"[round {round_index}] failed: {type(exc).__name__}: {exc}")

        round_failed = len(failures) - round_failure_count_before
        if round_failed:
            round_summaries.append(
                {
                    "round_index": round_index,
                    "planned_tasks": len(rescue.envelopes),
                    "succeeded_tasks": len(round_records),
                    "failed_tasks": round_failed,
                    "new_provider_calls": new_provider_calls - round_new_calls_before,
                    "registry_changed": False,
                }
            )
            termination_reason = "round_failure"
            break

        accumulated_supplemental.extend(_supplemental_decisions(round_decisions))
        current_registry = build_document_character_registry(
            preparation=preparation,
            grounded_decisions=base_decisions,
            supplemental_grounded_decisions=tuple(accumulated_supplemental),
        )
        registry_changed = _canonical_hash(current_registry) != registry_before_hash
        round_summaries.append(
            {
                "round_index": round_index,
                "planned_tasks": len(rescue.envelopes),
                "succeeded_tasks": len(round_records),
                "failed_tasks": 0,
                "new_provider_calls": new_provider_calls - round_new_calls_before,
                "registry_changed": registry_changed,
                "registry_summary": current_registry.get("summary"),
            }
        )
        if not registry_changed:
            fixed_point_reached = True
            termination_reason = "no_decisive_registry_change"
            break
        rescue = build_cluster_rescue_preparation(
            preparation=preparation,
            grounded_decisions=base_decisions,
            baseline_registry=current_registry,
            document_text=document_text,
            max_candidates_per_task=max_candidates_per_task,
            max_contexts_per_character=max_contexts_per_character,
            max_relationship_contexts_per_candidate=max_relationship_contexts_per_candidate,
            max_relationship_context_characters=max_relationship_context_characters,
        )
        if not rescue.envelopes:
            fixed_point_reached = True
            termination_reason = "no_pending_tasks"
            break

    _write_json(
        output_dir / "cluster-rescue-model-outputs.json",
        [
            {
                "task_index": item["task_index"],
                "round_index": item["round_index"],
                "task_cache_key": item["task_cache_key"],
                "subject_labels": item["subject_labels"],
                "model_output": item["model_output"],
            }
            for item in records
        ],
    )
    _write_json(
        output_dir / "grounded-cluster-rescue-decisions.json",
        [item.to_dict() for item in (*seeded_grounded, *new_grounded_decisions)],
    )
    _write_json(
        output_dir / "provider-traces.json",
        [item["provider_trace"] for item in records if item.get("provider_trace") is not None],
    )
    _write_json(output_dir / "failures.json", failures)
    _write_json(output_dir / "cluster-rescue-rounds.json", round_envelopes)
    complete = not failures
    registry = current_registry if complete else None
    if registry is not None:
        _write_json(output_dir / "document-character-registry.json", registry)
    relation_counts = {relation: 0 for relation in ("same_character", "different_characters", "uncertain")}
    new_relation_counts = dict(relation_counts)
    issue_counts: dict[str, int] = {}
    for decision in (*seeded_grounded, *new_grounded_decisions):
        relation_counts[decision.identity_relation] += 1
        for issue in decision.issues:
            issue_counts[issue.code] = issue_counts.get(issue.code, 0) + 1
    for decision in new_grounded_decisions:
        new_relation_counts[decision.identity_relation] += 1
    summary = {
        **preparation_summary,
        "schema_version": CLUSTER_RESCUE_BATCH_SUMMARY_VERSION,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "duration_ms": max(0, round((time.monotonic() - started_clock) * 1000)),
        "planned_tasks": total_planned_tasks,
        "succeeded_tasks": len(records),
        "failed_tasks": len(failures),
        "resumed_tasks": resumed_tasks,
        "new_provider_calls": new_provider_calls,
        "recorded_provider_calls": len(traces) - initial_trace_count if traces is not None else 0,
        "seeded_decisions": len(seeded_grounded),
        "identity_relations": relation_counts,
        "new_identity_relations": new_relation_counts,
        "grounding_issues": sum(issue_counts.values()),
        "grounding_issues_by_code": dict(sorted(issue_counts.items())),
        "complete": complete,
        "fixed_point_reached": fixed_point_reached,
        "termination_reason": termination_reason,
        "rounds_completed": len(round_summaries),
        "rounds": round_summaries,
        "registry_built": registry is not None,
        "baseline_registry_summary": initial_registry_summary,
        "registry_summary": registry.get("summary") if registry is not None else None,
        "quality_note": (
            "Only candidate-specific relationship_context_quotes may support rescue identity evidence; "
            "completion does not replace human identity quality evaluation."
        ),
    }
    _write_json(output_dir / "summary.json", summary)
    _append_history(output_dir, summary)
    return summary
