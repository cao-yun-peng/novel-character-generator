"""Run registry loading with fail-closed hash validation.

The web layer never mutates run artifacts. Every file referenced by
``runs/web-run-registry.json`` (curated, immutable) or a managed registry
written by the job pipeline is hash-verified before its content is used; a
mismatch or missing file raises :class:`WebRunError` and the HTTP layer maps
it to an explicit error envelope.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Mapping

from ..text import sha256_text

REQUIRED_ARTIFACTS = ("registry", "fact_groups", "appearance_states", "label_projection")
OPTIONAL_ARTIFACTS = ("document_evidence",)
_RUN_ID_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")


@dataclass(frozen=True)
class ArtifactRef:
    name: str
    path: Path
    sha256: str


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    display_name: str
    input_file: Path
    document_hash: str
    source_document_version_id: str
    snapshot_namespace: str
    artifacts: Mapping[str, ArtifactRef]


class WebRunError(Exception):
    """Registry or artifact integrity failure with a stable machine code."""

    def __init__(self, code: str, message: str, *, status_code: int = 500) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def read_utf8_text(path: Path) -> str:
    """Decode UTF-8 without universal-newline normalization (matches CLI loading)."""
    with path.open("r", encoding="utf-8", newline="") as source:
        return source.read()


def _validate_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise WebRunError("registry_invalid", f"{label} must be a 64-hex sha256 string")
    try:
        int(value, 16)
    except ValueError as error:
        raise WebRunError("registry_invalid", f"{label} must be a 64-hex sha256 string") from error
    return value


def _parse_artifact(name: str, value: object, base_dir: Path) -> ArtifactRef:
    if not isinstance(value, Mapping):
        raise WebRunError("registry_invalid", f"artifact {name} must be an object with path and sha256")
    raw_path = value.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise WebRunError("registry_invalid", f"artifact {name} is missing a path")
    digest = _validate_sha256(value.get("sha256"), f"artifact {name} sha256")
    path = (base_dir / raw_path).resolve()
    if not path.is_file():
        raise WebRunError("artifact_missing", f"artifact {name} file not found: {raw_path}", status_code=500)
    return ArtifactRef(name=name, path=path, sha256=digest)


class RunRepository:
    """Immutable, hash-verified view over curated and managed run registries.

    The curated registry is required and loaded once at construction. A managed
    registry (written by the job pipeline when a run is published) is optional
    and can be reloaded at runtime so newly published runs become queryable
    without restarting the process.
    """

    def __init__(self, registry_file: Path, *, base_dir: Path | None = None, managed_registry_file: Path | None = None) -> None:
        self._registry_file = registry_file.resolve()
        self._managed_registry_file = managed_registry_file.resolve() if managed_registry_file else None
        self._base_dir = base_dir.resolve() if base_dir else self._registry_file.parent.parent
        self._lock = threading.Lock()
        self._runs: dict[str, RunSpec] = {}
        self._order: list[str] = []
        self._artifact_cache: dict[Path, Mapping[str, object]] = {}
        self._text_cache: dict[Path, str] = {}
        self._load_registry()

    @property
    def registry_file(self) -> Path:
        return self._registry_file

    @property
    def managed_registry_file(self) -> Path | None:
        return self._managed_registry_file

    def reload(self) -> None:
        """Re-read managed registry entries (curated entries are immutable)."""
        with self._lock:
            self._load_registry()

    def _load_registry(self) -> None:
        runs: dict[str, RunSpec] = {}
        order: list[str] = []
        for entry in self._registry_entries(self._registry_file, required=True):
            self._insert_run(runs, order, entry, self._base_dir)
        if self._managed_registry_file is not None and self._managed_registry_file.is_file():
            # Managed entries are written by the pipeline with paths relative
            # to the managed registry's own grandparent (e.g. runs/).
            managed_base = self._managed_registry_file.parent.parent
            for entry in self._registry_entries(self._managed_registry_file, required=False):
                self._insert_run(runs, order, entry, managed_base)
        self._runs = runs
        self._order = order
        self._artifact_cache = {}
        self._text_cache = {}

    def _registry_entries(self, registry_file: Path, *, required: bool) -> list[object]:
        if not registry_file.is_file():
            if required:
                raise WebRunError("registry_missing", f"run registry not found: {registry_file}")
            return []
        try:
            payload = json.loads(registry_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WebRunError("registry_invalid", f"run registry unreadable: {error}") from error
        if not isinstance(payload, Mapping) or payload.get("schema_version") != "web-run-registry-v1":
            raise WebRunError("registry_invalid", f"run registry {registry_file.name} schema_version must be web-run-registry-v1")
        runs = payload.get("runs")
        if not isinstance(runs, list) or (required and not runs):
            raise WebRunError("registry_invalid", f"run registry {registry_file.name} must contain at least one run")
        return runs

    def _insert_run(self, runs: dict[str, RunSpec], order: list[str], entry: object, base_dir: Path) -> None:
        spec = self._parse_run(entry, base_dir)
        if spec.run_id in runs:
            raise WebRunError("registry_invalid", f"duplicate run_id: {spec.run_id}")
        runs[spec.run_id] = spec
        order.append(spec.run_id)

    def _parse_run(self, entry: object, base_dir: Path) -> RunSpec:
        if not isinstance(entry, Mapping):
            raise WebRunError("registry_invalid", "each run entry must be an object")
        run_id = entry.get("run_id")
        if not isinstance(run_id, str) or not run_id or not set(run_id) <= _RUN_ID_CHARS:
            raise WebRunError("registry_invalid", "run_id must be non-empty lowercase slug")
        display_name = entry.get("display_name", run_id)
        if not isinstance(display_name, str):
            raise WebRunError("registry_invalid", f"run {run_id} display_name must be a string")
        input_file = entry.get("input_file")
        if not isinstance(input_file, str) or not input_file:
            raise WebRunError("registry_invalid", f"run {run_id} is missing input_file")
        resolved_input = (base_dir / input_file).resolve()
        if not resolved_input.is_file():
            raise WebRunError("registry_invalid", f"run {run_id} input file not found: {input_file}")
        document_hash = _validate_sha256(entry.get("document_hash"), f"run {run_id} document_hash")
        source_version = entry.get("source_document_version_id")
        if not isinstance(source_version, str) or not source_version:
            raise WebRunError("registry_invalid", f"run {run_id} is missing source_document_version_id")
        namespace = entry.get("snapshot_namespace", run_id)
        if not isinstance(namespace, str) or not namespace:
            raise WebRunError("registry_invalid", f"run {run_id} snapshot_namespace must be a string")
        artifacts_payload = entry.get("artifacts")
        if not isinstance(artifacts_payload, Mapping):
            raise WebRunError("registry_invalid", f"run {run_id} is missing artifacts")
        artifacts: dict[str, ArtifactRef] = {}
        for name in REQUIRED_ARTIFACTS:
            if name not in artifacts_payload:
                raise WebRunError("registry_invalid", f"run {run_id} is missing required artifact {name}")
            artifacts[name] = _parse_artifact(name, artifacts_payload[name], base_dir)
        for name in OPTIONAL_ARTIFACTS:
            if name in artifacts_payload:
                artifacts[name] = _parse_artifact(name, artifacts_payload[name], base_dir)
        return RunSpec(
            run_id=run_id,
            display_name=display_name,
            input_file=resolved_input,
            document_hash=document_hash,
            source_document_version_id=source_version,
            snapshot_namespace=namespace,
            artifacts=artifacts,
        )

    @property
    def registry_file(self) -> Path:
        return self._registry_file

    def list_runs(self) -> list[RunSpec]:
        return [self._runs[run_id] for run_id in self._order]

    def get_run(self, run_id: str) -> RunSpec:
        spec = self._runs.get(run_id)
        if spec is None:
            raise WebRunError("run_not_found", f"unknown run_id: {run_id}", status_code=404)
        return spec

    def load_document_text(self, spec: RunSpec) -> str:
        cached = self._text_cache.get(spec.input_file)
        if cached is not None:
            return cached
        text = read_utf8_text(spec.input_file)
        actual = sha256_text(text)
        if actual != spec.document_hash:
            raise WebRunError(
                "document_hash_mismatch",
                f"document {spec.input_file.name} hash {actual} does not match registry",
            )
        self._text_cache[spec.input_file] = text
        return text

    def load_artifact(self, spec: RunSpec, name: str) -> Mapping[str, object]:
        ref = spec.artifacts.get(name)
        if ref is None:
            raise WebRunError("artifact_missing", f"run {spec.run_id} has no artifact {name}", status_code=404)
        cached = self._artifact_cache.get(ref.path)
        if cached is not None:
            return cached
        raw = ref.path.read_bytes()
        actual = sha256(raw).hexdigest()
        if actual != ref.sha256:
            raise WebRunError(
                "artifact_hash_mismatch",
                f"artifact {name} of run {spec.run_id} hash {actual} does not match registry",
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WebRunError("artifact_invalid", f"artifact {name} of run {spec.run_id} is not valid JSON: {error}") from error
        if not isinstance(payload, dict):
            raise WebRunError("artifact_invalid", f"artifact {name} of run {spec.run_id} must be a JSON object")
        self._artifact_cache[ref.path] = payload
        return payload
