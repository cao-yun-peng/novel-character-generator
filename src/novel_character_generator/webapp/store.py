"""Persistent storage for managed documents, jobs, and subject mappings.

Layout under the workspace root (default ``runs/web-jobs``)::

    web-job-registry.json     managed run registry (schema web-run-registry-v1)
    idempotency.json          Idempotency-Key -> job request fingerprint
    documents/{doc}/document.json
    documents/{doc}/versions/{version}/source.txt   (immutable)
    documents/{doc}/versions/{version}/version.json
    documents/{doc}/subjects.json
    jobs/{job}/job.json       atomic job record
    jobs/{job}/events.jsonl   append-only progress events

All writes go through atomic tmp+replace. Document version files are
content-addressed and written exactly once; any later mismatch fails closed.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..text import sha256_text
from .repository import read_utf8_text

JOB_RECORD_VERSION = "web-job-record-v1"
SUBJECT_INDEX_VERSION = "document-subject-index-v1"
IDEMPOTENCY_INDEX_VERSION = "web-job-idempotency-v1"
DOCUMENT_META_VERSION = "web-document-meta-v1"
DECISION_LOG_VERSION = "web-review-decision-log-v1"

JOB_STATUSES = ("queued", "running", "succeeded", "partial", "failed", "cancelled")
STAGE_STATUSES = ("pending", "running", "succeeded", "partial", "failed", "cancelled", "skipped")
TERMINAL_JOB_STATUSES = ("succeeded", "partial", "failed", "cancelled")
ACTIVE_JOB_STATUSES = ("queued", "running")

DECISION_ACTIONS = ("accept", "reject", "correct", "reopen")

DOCUMENT_ID_PATTERN = re.compile(r"^doc-[0-9a-f]{12}$")
VERSION_ID_PATTERN = re.compile(r"^source-[0-9a-f]{16}$")
JOB_ID_PATTERN = re.compile(r"^job-[0-9a-f]{12}$")
SUBJECT_ID_PATTERN = re.compile(r"^subj-[0-9a-f]{12}$")
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")

MAX_DOCUMENT_CODE_POINTS = 5_000_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class StoreError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------- documents


@dataclass(frozen=True)
class DocumentVersion:
    document_id: str
    version_id: str
    document_hash: str
    code_points: int
    created_at: str
    source_path: Path


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    display_name: str
    created_at: str
    versions: tuple[DocumentVersion, ...]

    @property
    def latest_version(self) -> DocumentVersion | None:
        return self.versions[-1] if self.versions else None


class DocumentStore:
    """Immutable, content-addressed source document versions."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._documents_dir = self._root / "documents"
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        return self._root

    @staticmethod
    def document_id_for(document_hash: str) -> str:
        return f"doc-{document_hash[:12]}"

    @staticmethod
    def version_id_for(document_hash: str) -> str:
        return f"source-{document_hash[:16]}"

    def create_version(self, text: str, *, display_name: str) -> tuple[DocumentVersion, bool]:
        """Store ``text``; identical content is idempotent. Returns (version, created)."""
        if not text:
            raise StoreError("document_empty", "document text must be non-empty", status_code=422)
        total = len(text)
        if total > MAX_DOCUMENT_CODE_POINTS:
            raise StoreError(
                "document_too_large",
                f"document has {total} code points, exceeding the limit of {MAX_DOCUMENT_CODE_POINTS}",
                status_code=422,
            )
        document_hash = sha256_text(text)
        document_id = self.document_id_for(document_hash)
        version_id = self.version_id_for(document_hash)
        with self._lock:
            document_dir = self._documents_dir / document_id
            version_dir = document_dir / "versions" / version_id
            source_path = version_dir / "source.txt"
            created = not source_path.exists()
            if created:
                version_dir.mkdir(parents=True, exist_ok=True)
                # CRLF fidelity: write text verbatim without newline translation.
                temporary = source_path.with_name(".source.txt.tmp")
                with temporary.open("w", encoding="utf-8", newline="") as handle:
                    handle.write(text)
                os.replace(temporary, source_path)
                _atomic_write_json(version_dir / "version.json", {
                    "schema_version": DOCUMENT_META_VERSION,
                    "document_id": document_id,
                    "version_id": version_id,
                    "document_hash": document_hash,
                    "code_points": total,
                    "created_at": utc_now(),
                })
            if not (document_dir / "document.json").exists():
                _atomic_write_json(document_dir / "document.json", {
                    "schema_version": DOCUMENT_META_VERSION,
                    "document_id": document_id,
                    "display_name": display_name or version_id,
                    "created_at": utc_now(),
                })
            return self._load_version(document_id, version_id), created

    def list_documents(self) -> list[DocumentRecord]:
        if not self._documents_dir.is_dir():
            return []
        records: list[DocumentRecord] = []
        for document_dir in sorted(self._documents_dir.iterdir()):
            if not document_dir.is_dir() or not DOCUMENT_ID_PATTERN.match(document_dir.name):
                continue
            record = self._load_document(document_dir.name)
            if record is not None:
                records.append(record)
        return records

    def get_document(self, document_id: str) -> DocumentRecord:
        if not DOCUMENT_ID_PATTERN.match(document_id):
            raise StoreError("document_not_found", f"unknown document_id: {document_id}", status_code=404)
        record = self._load_document(document_id)
        if record is None:
            raise StoreError("document_not_found", f"unknown document_id: {document_id}", status_code=404)
        return record

    def get_version(self, document_id: str, version_id: str) -> DocumentVersion:
        record = self.get_document(document_id)
        for version in record.versions:
            if version.version_id == version_id:
                return version
        raise StoreError(
            "version_not_found",
            f"document {document_id} has no version {version_id}",
            status_code=404,
        )

    def load_text(self, version: DocumentVersion) -> str:
        text = read_utf8_text(version.source_path)
        actual = sha256_text(text)
        if actual != version.document_hash:
            raise StoreError(
                "document_hash_mismatch",
                f"stored source of {version.version_id} hashes to {actual}, expected {version.document_hash}",
                status_code=500,
            )
        return text

    def find_by_document_hash(self, document_hash: str) -> DocumentRecord | None:
        document_id = self.document_id_for(document_hash)
        if (self._documents_dir / document_id / "document.json").is_file():
            return self.get_document(document_id)
        return None

    def _load_document(self, document_id: str) -> DocumentRecord | None:
        document_dir = self._documents_dir / document_id
        meta_path = document_dir / "document.json"
        if not meta_path.is_file():
            return None
        meta = _read_json(meta_path)
        versions: list[DocumentVersion] = []
        versions_dir = document_dir / "versions"
        if versions_dir.is_dir():
            for version_dir in sorted(versions_dir.iterdir()):
                if not version_dir.is_dir():
                    continue
                version = self._load_version(document_id, version_dir.name, strict=False)
                if version is not None:
                    versions.append(version)
        versions.sort(key=lambda item: item.created_at)
        return DocumentRecord(
            document_id=document_id,
            display_name=str(meta.get("display_name") or document_id),
            created_at=str(meta.get("created_at") or ""),
            versions=tuple(versions),
        )

    def _load_version(self, document_id: str, version_id: str, *, strict: bool = True) -> DocumentVersion:
        version_dir = self._documents_dir / document_id / "versions" / version_id
        if not VERSION_ID_PATTERN.match(version_id) or not (version_dir / "version.json").is_file():
            if strict:
                raise StoreError("version_not_found", f"unknown version: {version_id}", status_code=404)
            return None  # type: ignore[return-value]
        payload = _read_json(version_dir / "version.json")
        return DocumentVersion(
            document_id=document_id,
            version_id=version_id,
            document_hash=str(payload["document_hash"]),
            code_points=int(payload["code_points"]),
            created_at=str(payload.get("created_at") or ""),
            source_path=version_dir / "source.txt",
        )


# --------------------------------------------------------------------- jobs


@dataclass
class StageState:
    stage_id: str
    name: str
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    progress_done: int = 0
    progress_total: int | None = None
    provider_calls: int = 0
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "progress": {"done": self.progress_done, "total": self.progress_total},
            "provider_calls": self.provider_calls,
            "summary": self.summary,
        }


def _pipeline_stages() -> list[StageState]:
    return [
        StageState("m1", "M1 提及抽取"),
        StageState("m2", "M2 外貌归属"),
        StageState("n3", "N3 认领与晋升"),
        StageState("evidence", "证据聚合"),
        StageState("identity", "M3 身份裁决"),
        StageState("identity_rescue", "簇救援裁决"),
        StageState("local_closure", "本地共指闭包"),
        StageState("fact_groups", "事实分组"),
        StageState("appearance_scopes", "外貌范围"),
        StageState("transitions", "状态转换发现"),
        StageState("label_projection", "标签复核投影"),
    ]


@dataclass
class JobRecord:
    job_id: str
    run_id: str
    document_id: str
    version_id: str
    document_hash: str
    display_name: str
    pipeline: dict[str, Any]
    idempotency_key: str | None = None
    status: str = "queued"
    cancel_requested: bool = False
    stages: list[StageState] = field(default_factory=_pipeline_stages)
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    completed_at: str | None = None

    def stage(self, stage_id: str) -> StageState:
        for item in self.stages:
            if item.stage_id == stage_id:
                return item
        raise StoreError("stage_not_found", f"unknown stage: {stage_id}", status_code=500)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": JOB_RECORD_VERSION,
            "job_id": self.job_id,
            "run_id": self.run_id,
            "document_id": self.document_id,
            "source_document_version_id": self.version_id,
            "document_hash": self.document_hash,
            "display_name": self.display_name,
            "pipeline": self.pipeline,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "cancel_requested": self.cancel_requested,
            "stages": [stage.to_dict() for stage in self.stages],
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobRecord":
        stages = [
            StageState(
                stage_id=str(item["stage_id"]),
                name=str(item["name"]),
                status=str(item.get("status") or "pending"),
                started_at=item.get("started_at"),
                completed_at=item.get("completed_at"),
                error=item.get("error"),
                progress_done=int(item.get("progress", {}).get("done") or 0),
                progress_total=item.get("progress", {}).get("total"),
                provider_calls=int(item.get("provider_calls") or 0),
                summary=dict(item.get("summary") or {}),
            )
            for item in payload.get("stages", [])
        ]
        return cls(
            job_id=str(payload["job_id"]),
            run_id=str(payload["run_id"]),
            document_id=str(payload["document_id"]),
            version_id=str(payload["source_document_version_id"]),
            document_hash=str(payload["document_hash"]),
            display_name=str(payload["display_name"]),
            pipeline=dict(payload.get("pipeline") or {}),
            idempotency_key=payload.get("idempotency_key"),
            status=str(payload.get("status") or "queued"),
            cancel_requested=bool(payload.get("cancel_requested")),
            stages=stages,
            error=payload.get("error"),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            started_at=payload.get("started_at"),
            completed_at=payload.get("completed_at"),
        )


class JobStore:
    """Atomic job records plus append-only per-job event logs."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._jobs_dir = self._root / "jobs"
        self._lock = threading.Lock()
        self._event_locks: dict[str, threading.Lock] = {}
        self._event_seq: dict[str, int] = {}

    @property
    def root(self) -> Path:
        return self._root

    def new_job_id(self) -> str:
        return f"job-{uuid.uuid4().hex[:12]}"

    def job_dir(self, job_id: str) -> Path:
        if not JOB_ID_PATTERN.match(job_id):
            raise StoreError("job_not_found", f"unknown job_id: {job_id}", status_code=404)
        return self._jobs_dir / job_id

    def create(self, record: JobRecord) -> None:
        path = self.job_dir(record.job_id) / "job.json"
        if path.exists():
            raise StoreError("job_exists", f"job {record.job_id} already exists", status_code=500)
        self.save(record)

    def save(self, record: JobRecord) -> None:
        record.updated_at = utc_now()
        _atomic_write_json(self.job_dir(record.job_id) / "job.json", record.to_dict())

    def get(self, job_id: str) -> JobRecord:
        path = self.job_dir(job_id) / "job.json"
        if not path.is_file():
            raise StoreError("job_not_found", f"unknown job_id: {job_id}", status_code=404)
        try:
            payload = _read_json(path)
        except json.JSONDecodeError as error:
            raise StoreError("job_invalid", f"job {job_id} record is unreadable: {error}", status_code=500) from error
        return JobRecord.from_dict(payload)

    def list_jobs(self) -> list[JobRecord]:
        jobs: list[JobRecord] = []
        if not self._jobs_dir.is_dir():
            return jobs
        for job_dir in sorted(self._jobs_dir.iterdir()):
            if job_dir.is_dir() and JOB_ID_PATTERN.match(job_dir.name):
                jobs.append(self.get(job_dir.name))
        jobs.sort(key=lambda item: item.created_at, reverse=True)
        return jobs

    # -------------------------------------------------------------- events

    def _event_file(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "events.jsonl"

    def append_event(
        self, job_id: str, event_type: str, *, stage_id: str | None = None,
        message: str | None = None, data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            lock = self._event_locks.setdefault(job_id, threading.Lock())
        with lock:
            seq = self._event_seq.get(job_id)
            if seq is None:
                seq = self._last_seq_from_file(job_id)
            seq += 1
            self._event_seq[job_id] = seq
            event = {
                "seq": seq,
                "at": utc_now(),
                "type": event_type,
                "stage_id": stage_id,
                "message": message,
                "data": dict(data) if data else {},
            }
            path = self._event_file(job_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            return event

    def read_events(self, job_id: str, *, after: int = 0) -> list[dict[str, Any]]:
        path = self._event_file(job_id)
        if not path.is_file():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if isinstance(event, dict) and int(event.get("seq") or 0) > after:
                events.append(event)
        return events

    def _last_seq_from_file(self, job_id: str) -> int:
        path = self._event_file(job_id)
        if not path.is_file():
            return 0
        last = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                last = max(last, int(json.loads(line).get("seq") or 0))
            except json.JSONDecodeError:
                continue
        return last

    # -------------------------------------------------- idempotency index

    def _idempotency_file(self) -> Path:
        return self._root / "idempotency.json"

    def lookup_idempotency(self, key: str) -> dict[str, Any] | None:
        path = self._idempotency_file()
        if not path.is_file():
            return None
        payload = _read_json(path)
        entry = payload.get(key)
        return dict(entry) if isinstance(entry, Mapping) else None

    def register_idempotency(self, key: str, job_id: str, fingerprint: str) -> None:
        with self._lock:
            path = self._idempotency_file()
            payload: dict[str, Any] = {}
            if path.is_file():
                loaded = _read_json(path)
                if isinstance(loaded, dict):
                    payload = dict(loaded)
            payload.setdefault("schema_version", IDEMPOTENCY_INDEX_VERSION)
            payload[key] = {"job_id": job_id, "request_fingerprint": fingerprint}
            _atomic_write_json(path, payload)


# ---------------------------------------------------------------- subjects


@dataclass(frozen=True)
class SubjectEntry:
    subject_id: str
    preferred_label: str
    status: str
    run_mappings: tuple[Mapping[str, Any], ...]


class SubjectIndex:
    """Stable subject_id <-> run-scoped character_id mappings (R08).

    Mapping rule for this milestone: a subject maps a character only when the
    exact character_id already belongs to that subject in a previous run of the
    same document (deterministic re-runs). Name collisions never merge
    silently; they create separate subjects and are surfaced as candidates.
    """

    def __init__(self, document_store: DocumentStore) -> None:
        self._documents = document_store
        self._lock = threading.Lock()

    @staticmethod
    def subject_id_for(document_hash: str, character_id: str) -> str:
        digest = sha256(f"{document_hash}:{character_id}".encode("utf-8")).hexdigest()
        return f"subj-{digest[:12]}"

    def _index_path(self, document_id: str) -> Path:
        return self._documents.root / "documents" / document_id / "subjects.json"

    def _load(self, document_id: str) -> dict[str, Any]:
        path = self._index_path(document_id)
        if not path.is_file():
            return {"schema_version": SUBJECT_INDEX_VERSION, "document_id": document_id, "subjects": []}
        payload = _read_json(path)
        if payload.get("schema_version") != SUBJECT_INDEX_VERSION:
            raise StoreError("subject_index_invalid", f"subject index of {document_id} has unsupported schema", status_code=500)
        return payload

    def record_run(self, document_id: str, run_id: str, characters: Sequence[Mapping[str, Any]]) -> None:
        """Extend the index with registry characters of a published run."""
        with self._lock:
            payload = self._load(document_id)
            subjects: list[dict[str, Any]] = list(payload.get("subjects") or [])
            for entry in characters:
                character_id = str(entry.get("character_id") or "")
                if not character_id:
                    continue
                existing = self._find_by_character(subjects, character_id)
                mapping = {"run_id": run_id, "character_id": character_id, "resolved_at": utc_now()}
                if existing is None:
                    subjects.append({
                        "subject_id": None,
                        "preferred_label": str(entry.get("canonical_label") or character_id),
                        "status": "active",
                        "run_mappings": [mapping],
                    })
                else:
                    known_runs = {str(item.get("run_id")) for item in existing.get("run_mappings") or []}
                    if run_id not in known_runs:
                        existing["run_mappings"].append(mapping)
            if subjects:
                document_hash = self._document_hash_for(document_id)
                for subject in subjects:
                    if subject.get("subject_id") is None:
                        first = subject["run_mappings"][0]
                        subject["subject_id"] = self.subject_id_for(document_hash, str(first["character_id"]))
            payload["subjects"] = subjects
            _atomic_write_json(self._index_path(document_id), payload)

    def _document_hash_for(self, document_id: str) -> str:
        record = self._documents.get_document(document_id)
        if record.latest_version is None:
            raise StoreError("document_no_versions", f"document {document_id} has no versions", status_code=500)
        return record.latest_version.document_hash

    @staticmethod
    def _find_by_character(subjects: list[dict[str, Any]], character_id: str) -> dict[str, Any] | None:
        for subject in subjects:
            for mapping in subject.get("run_mappings") or []:
                if str(mapping.get("character_id")) == character_id:
                    return subject
        return None

    def list_subjects(self, document_id: str) -> list[SubjectEntry]:
        payload = self._load(document_id)
        entries: list[SubjectEntry] = []
        for subject in payload.get("subjects") or []:
            entries.append(SubjectEntry(
                subject_id=str(subject["subject_id"]),
                preferred_label=str(subject.get("preferred_label") or ""),
                status=str(subject.get("status") or "active"),
                run_mappings=tuple(subject.get("run_mappings") or []),
            ))
        return entries

    def get_subject(self, document_id: str, subject_id: str) -> SubjectEntry:
        for entry in self.list_subjects(document_id):
            if entry.subject_id == subject_id:
                return entry
        raise StoreError("subject_not_found", f"unknown subject_id: {subject_id}", status_code=404)

    def resolve_character(self, document_id: str, run_id: str, character_id: str) -> str | None:
        for entry in self.list_subjects(document_id):
            for mapping in entry.run_mappings:
                if str(mapping.get("run_id")) == run_id and str(mapping.get("character_id")) == character_id:
                    return entry.subject_id
        return None


# --------------------------------------------------------------- decisions


@dataclass(frozen=True)
class ReviewDecision:
    decision_id: str
    run_id: str
    review_id: str
    target_kind: str
    action: str
    operator: str
    note: str
    payload: Mapping[str, Any]
    revision: int
    idempotency_key: str | None
    request_fingerprint: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "review_id": self.review_id,
            "target_kind": self.target_kind,
            "action": self.action,
            "operator": self.operator,
            "note": self.note,
            "payload": dict(self.payload),
            "revision": self.revision,
            "idempotency_key": self.idempotency_key,
            "request_fingerprint": self.request_fingerprint,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReviewDecision":
        return cls(
            decision_id=str(payload["decision_id"]),
            run_id=str(payload["run_id"]),
            review_id=str(payload["review_id"]),
            target_kind=str(payload["target_kind"]),
            action=str(payload["action"]),
            operator=str(payload.get("operator") or ""),
            note=str(payload.get("note") or ""),
            payload=dict(payload.get("payload") or {}),
            revision=int(payload["revision"]),
            idempotency_key=payload.get("idempotency_key"),
            request_fingerprint=str(payload.get("request_fingerprint") or ""),
            created_at=str(payload.get("created_at") or ""),
        )


def decision_fingerprint(
    review_id: str, action: str, operator: str, payload: Mapping[str, Any],
) -> str:
    canonical = json.dumps(
        {"review_id": review_id, "action": action, "operator": operator, "payload": dict(payload)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


class ReviewDecisionStore:
    """Append-only, versioned human decision log per run (R11).

    Decisions never modify run artifacts, raw facts, or model outputs; the log
    only grows. Optimistic locking: every submit must carry the revision the
    client expects; a mismatch fails closed with ``version_conflict``. A
    decided review is reopened by appending a ``reopen`` compensation decision,
    never by editing or deleting history.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._decisions_dir = self._root / "decisions"
        self._lock = threading.Lock()

    def _log_path(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.match(run_id):
            raise StoreError("run_id_invalid", f"run_id has unsupported characters: {run_id}", status_code=400)
        return self._decisions_dir / run_id / "decision-log.json"

    def _load(self, run_id: str) -> dict[str, Any]:
        path = self._log_path(run_id)
        if not path.is_file():
            return {
                "schema_version": DECISION_LOG_VERSION,
                "run_id": run_id,
                "revision": 0,
                "decisions": [],
            }
        payload = _read_json(path)
        if payload.get("schema_version") != DECISION_LOG_VERSION:
            raise StoreError(
                "decision_log_invalid",
                f"decision log of run {run_id} has unsupported schema",
                status_code=500,
            )
        return payload

    def current_revision(self, run_id: str) -> int:
        with self._lock:
            return int(self._load(run_id).get("revision") or 0)

    def list_decisions(self, run_id: str, *, review_id: str | None = None) -> list[ReviewDecision]:
        with self._lock:
            payload = self._load(run_id)
        decisions = [ReviewDecision.from_dict(item) for item in payload.get("decisions") or []]
        if review_id is None:
            return decisions
        return [item for item in decisions if item.review_id == review_id]

    def submit(
        self,
        run_id: str,
        *,
        review_id: str,
        target_kind: str,
        action: str,
        operator: str,
        note: str,
        payload: Mapping[str, Any],
        expected_revision: int,
        idempotency_key: str | None,
    ) -> tuple[ReviewDecision, bool]:
        if action not in DECISION_ACTIONS:
            raise StoreError(
                "decision_action_invalid",
                f"action must be one of {DECISION_ACTIONS}, got: {action}",
                status_code=422,
            )
        if not str(operator).strip():
            raise StoreError("decision_operator_required", "operator must be a non-empty name", status_code=422)
        fingerprint = decision_fingerprint(review_id, action, operator, payload)
        with self._lock:
            log = self._load(run_id)
            revision = int(log.get("revision") or 0)
            if idempotency_key:
                for item in log.get("decisions") or []:
                    if item.get("idempotency_key") == idempotency_key:
                        existing = ReviewDecision.from_dict(item)
                        if existing.request_fingerprint == fingerprint:
                            return existing, False
                        raise StoreError(
                            "decision_key_conflict",
                            f"idempotency key already used by decision {existing.decision_id} with a different request",
                            status_code=409,
                        )
            if expected_revision != revision:
                raise StoreError(
                    "version_conflict",
                    f"expected revision {expected_revision} but decision log is at {revision}; "
                    "reload the review list and retry",
                    status_code=409,
                )
            revision += 1
            decision = ReviewDecision(
                decision_id=f"decision-{uuid.uuid4().hex[:12]}",
                run_id=run_id,
                review_id=review_id,
                target_kind=target_kind,
                action=action,
                operator=operator,
                note=note,
                payload=dict(payload),
                revision=revision,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                created_at=utc_now(),
            )
            log["revision"] = revision
            log["decisions"] = list(log.get("decisions") or []) + [decision.to_dict()]
            _atomic_write_json(self._log_path(run_id), log)
            return decision, True
