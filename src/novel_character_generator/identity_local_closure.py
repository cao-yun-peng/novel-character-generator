from __future__ import annotations

import copy
import json
from hashlib import sha256
from pathlib import Path
from typing import Mapping

from .document_profiles import run_document_profile_assembly
from .errors import ContractValidationError
from .identity import (
    IDENTITY_CANDIDATE_POLICY_VERSION,
    IDENTITY_LOCAL_COREFERENCE_POLICY_VERSION,
    IDENTITY_POLICY_VERSION,
    apply_local_coreference_to_preparation,
    build_document_character_registry,
)
from .identity_rescue_batch import (
    _parse_cluster_rescue_decisions,
    _supplemental_decisions,
    load_saved_identity_run,
)

LOCAL_IDENTITY_CLOSURE_MANIFEST_VERSION = "local-identity-closure-manifest-v1"
LOCAL_IDENTITY_CLOSURE_SUMMARY_VERSION = "local-identity-closure-summary-v1"


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
        raise ContractValidationError(f"cannot hash local identity closure source artifact {path}") from exc


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def run_local_identity_closure_replay(
    *,
    document_text: str,
    source_identity_run_dir: Path,
    source_rescue_run_dir: Path,
    evidence_file: Path,
    output_dir: Path,
    max_local_coreference_characters: int = 600,
) -> dict[str, object]:
    """Replay saved grounded identity decisions with current deterministic local closure."""
    if max_local_coreference_characters < 1:
        raise ContractValidationError("max_local_coreference_characters must be positive")
    preparation, base_decisions, base_artifacts = load_saved_identity_run(
        document_text=document_text,
        source_identity_run_dir=source_identity_run_dir,
    )
    rescue_decisions_path = source_rescue_run_dir / "grounded-cluster-rescue-decisions.json"
    cluster_decisions = _parse_cluster_rescue_decisions(
        _read_json(rescue_decisions_path),
        document_text=document_text,
    )
    supplemental_decisions = _supplemental_decisions(cluster_decisions)
    baseline_registry = build_document_character_registry(
        preparation=preparation,
        grounded_decisions=base_decisions,
        supplemental_grounded_decisions=supplemental_decisions,
    )
    updated_preparation = apply_local_coreference_to_preparation(
        preparation=preparation,
        document_text=document_text,
        max_characters=max_local_coreference_characters,
    )
    registry = build_document_character_registry(
        preparation=updated_preparation,
        grounded_decisions=base_decisions,
        supplemental_grounded_decisions=supplemental_decisions,
    )

    old_pairs = {
        frozenset({str(edge["left_node_key"]), str(edge["right_node_key"])})
        for edge in preparation.deterministic_edges
    }
    local_edges = [
        copy.deepcopy(dict(edge))
        for edge in updated_preparation.deterministic_edges
        if edge.get("reason") == "explicit_local_coreference"
        and frozenset({str(edge["left_node_key"]), str(edge["right_node_key"])}) not in old_pairs
    ]
    source_artifacts = {
        **copy.deepcopy(dict(base_artifacts)),
        "grounded_cluster_rescue_decisions": {
            "path": str(rescue_decisions_path.resolve()),
            "hash": _file_hash(rescue_decisions_path),
        },
        "document_character_evidence": {
            "path": str(evidence_file.resolve()),
            "hash": _file_hash(evidence_file),
        },
    }
    manifest = {
        "schema_version": LOCAL_IDENTITY_CLOSURE_MANIFEST_VERSION,
        "identity_policy_version": IDENTITY_POLICY_VERSION,
        "candidate_policy_version": IDENTITY_CANDIDATE_POLICY_VERSION,
        "local_coreference_policy_version": IDENTITY_LOCAL_COREFERENCE_POLICY_VERSION,
        "source_document_version_id": updated_preparation.local_nodes.source_document_version_id,
        "document_hash": updated_preparation.local_nodes.document_hash,
        "configuration": {
            "max_local_coreference_characters": max_local_coreference_characters,
        },
        "source_artifacts": source_artifacts,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "local-identity-closure-manifest.json"
    if manifest_path.exists() and _read_json(manifest_path) != manifest:
        raise ContractValidationError("existing local identity closure output sources do not match")
    _write_json(manifest_path, manifest)
    _write_json(output_dir / "local-coreference-edges.json", local_edges)
    _write_json(
        output_dir / "identity-deterministic-edges.json",
        list(updated_preparation.deterministic_edges),
    )
    registry_path = output_dir / "document-character-registry.json"
    profiles_path = output_dir / "document-character-profiles.json"
    _write_json(registry_path, registry)
    profile_summary = run_document_profile_assembly(
        document_text=document_text,
        registry_file=registry_path,
        evidence_file=evidence_file,
        output_file=profiles_path,
    )
    summary = {
        "schema_version": LOCAL_IDENTITY_CLOSURE_SUMMARY_VERSION,
        "identity_policy_version": IDENTITY_POLICY_VERSION,
        "candidate_policy_version": IDENTITY_CANDIDATE_POLICY_VERSION,
        "local_coreference_policy_version": IDENTITY_LOCAL_COREFERENCE_POLICY_VERSION,
        "base_grounded_identity_decisions": len(base_decisions),
        "supplemental_grounded_identity_decisions": len(supplemental_decisions),
        "deterministic_edges_before": len(preparation.deterministic_edges),
        "deterministic_edges_after": len(updated_preparation.deterministic_edges),
        "new_local_coreference_edges": len(local_edges),
        "baseline_registry_summary": copy.deepcopy(
            dict(_mapping(baseline_registry.get("summary"), "baseline registry summary"))
        ),
        "registry_summary": copy.deepcopy(dict(_mapping(registry.get("summary"), "registry summary"))),
        "profile_summary": copy.deepcopy(dict(_mapping(profile_summary, "profile summary"))),
        "provider_calls": 0,
        "complete": True,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary
