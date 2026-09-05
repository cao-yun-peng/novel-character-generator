"""Managed job orchestration (R09): submit, cancel, resume, events, recovery.

The service owns a single background worker thread so at most one job runs at
a time — provider quota and stage artifacts are never contended by two
executors (docs/37 section 6.2 lease requirement). All state transitions are
persisted through :class:`~novel_character_generator.webapp.store.JobStore`
before the in-memory queue is touched, so a crash never loses a job: any
``queued``/``running`` record found at startup is re-enqueued (or finalized as
cancelled when the user had already requested cancellation).

Cancellation of a running job is cooperative: the service sets an in-memory
event the executor polls before each stage and inside progress sinks, plus a
``cancel.flag`` file that survives crashes. The service never rewrites
``job.json`` of a job the worker is currently executing, avoiding write races
with the executor.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from queue import Queue
from typing import Any, Mapping

from ..text import sha256_text
from .pipeline import PipelineExecutor
from .store import (
    ACTIVE_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    DocumentStore,
    JobRecord,
    JobStore,
    StoreError,
    SubjectIndex,
    utc_now,
)

PIPELINE_CONFIG_KEYS = ("chunk_size", "overlap_characters")
DEFAULT_CHUNK_SIZE = 8000
DEFAULT_OVERLAP_CHARACTERS = 500
CHUNK_SIZE_BOUNDS = (1_000, 200_000)
OVERLAP_BOUNDS = (0, 20_000)
MAX_IDEMPOTENCY_KEY_LENGTH = 200


def request_fingerprint(document_id: str, version_id: str, pipeline: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {"document_id": document_id, "version_id": version_id, "pipeline": dict(pipeline)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha256_text(payload)


def build_run_id(display_name: str, job_id: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", display_name.lower()).strip("-")[:40].strip("-")
    return f"{slug or 'web'}-{job_id[len('job-'):]}"


def validated_pipeline(pipeline: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(pipeline or {})
    unknown = sorted(set(source) - set(PIPELINE_CONFIG_KEYS))
    if unknown:
        raise StoreError("invalid_pipeline_config", f"unsupported pipeline options: {unknown}", status_code=422)
    config: dict[str, Any] = {}
    bounds = {
        "chunk_size": CHUNK_SIZE_BOUNDS,
        "overlap_characters": OVERLAP_BOUNDS,
    }
    defaults = {"chunk_size": DEFAULT_CHUNK_SIZE, "overlap_characters": DEFAULT_OVERLAP_CHARACTERS}
    for key in PIPELINE_CONFIG_KEYS:
        value = source.get(key, defaults[key])
        low, high = bounds[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise StoreError(
                "invalid_pipeline_config",
                f"{key} must be an integer in [{low}, {high}], got {value!r}",
                status_code=422,
            )
        config[key] = value
    return config


class JobService:
    def __init__(
        self,
        *,
        document_store: DocumentStore,
        job_store: JobStore,
        subject_index: SubjectIndex,
        executor: PipelineExecutor,
    ) -> None:
        self._documents = document_store
        self._jobs = job_store
        self._subjects = subject_index
        self._executor = executor
        self._queue: Queue[str | None] = Queue()
        self._dispatch_lock = threading.Lock()
        self._active: set[str] = set()
        self._cancel_events: dict[str, threading.Event] = {}
        self._thread: threading.Thread | None = None
        self._stopping = False

    @property
    def documents(self) -> DocumentStore:
        return self._documents

    @property
    def subjects(self) -> SubjectIndex:
        return self._subjects

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._dispatch_lock:
            self._stopping = False
        self._thread = threading.Thread(target=self._worker_loop, name="novel-job-worker", daemon=True)
        self._thread.start()

    def shutdown(self, *, timeout: float = 10.0) -> None:
        with self._dispatch_lock:
            self._stopping = True
        self._queue.put(None)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)

    def startup_recover(self) -> list[str]:
        """Re-enqueue jobs left queued/running by a previous process crash."""
        recovered: list[str] = []
        for job in sorted(self._jobs.list_jobs(), key=lambda item: item.created_at):
            if job.status not in ACTIVE_JOB_STATUSES:
                continue
            with self._dispatch_lock:
                if job.job_id in self._active:
                    continue
                if self._cancel_requested(job.job_id):
                    self._finalize_cancel(job)
                    continue
                previous_status = job.status
                for stage in job.stages:
                    if stage.status == "running":
                        stage.status = "pending"
                        stage.started_at = None
                job.status = "queued"
                job.error = None
                job.completed_at = None
                self._jobs.save(job)
                self._jobs.append_event(job.job_id, "job_recovered", data={"previous_status": previous_status})
            self._enqueue(job.job_id)
            recovered.append(job.job_id)
        return recovered

    # ---------------------------------------------------------------- submit

    def submit_job(
        self,
        document_id: str,
        version_id: str | None = None,
        *,
        pipeline: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[JobRecord, bool]:
        config = validated_pipeline(pipeline)
        document = self._documents.get_document(document_id)
        if version_id is None:
            latest = document.latest_version
            if latest is None:
                raise StoreError(
                    "document_no_versions",
                    f"document {document_id} has no source versions",
                    status_code=409,
                )
            version = latest
        else:
            version = self._documents.get_version(document_id, version_id)

        key = idempotency_key.strip() if idempotency_key else ""
        if idempotency_key is not None and (not key or len(key) > MAX_IDEMPOTENCY_KEY_LENGTH):
            raise StoreError(
                "invalid_idempotency_key",
                f"Idempotency-Key must be 1..{MAX_IDEMPOTENCY_KEY_LENGTH} characters",
                status_code=422,
            )
        fingerprint = request_fingerprint(document_id, version.version_id, config)
        if key:
            entry = self._jobs.lookup_idempotency(key)
            if entry is not None:
                if entry.get("request_fingerprint") == fingerprint:
                    return self.get_job(str(entry["job_id"])), False
                raise StoreError(
                    "idempotency_conflict",
                    f"Idempotency-Key was already used for job {entry.get('job_id')} with a different request",
                    status_code=409,
                )

        self._reject_active_conflict(document_id, version.version_id, exclude=None)

        job_id = self._jobs.new_job_id()
        job = JobRecord(
            job_id=job_id,
            run_id=build_run_id(document.display_name, job_id),
            document_id=document_id,
            version_id=version.version_id,
            document_hash=version.document_hash,
            display_name=document.display_name,
            pipeline=config,
            idempotency_key=key or None,
        )
        self._jobs.create(job)
        self._jobs.append_event(
            job.job_id,
            "job_created",
            data={"run_id": job.run_id, "source_document_version_id": version.version_id},
        )
        if key:
            self._jobs.register_idempotency(key, job_id, fingerprint)
        self._enqueue(job_id)
        return job, True

    def _reject_active_conflict(self, document_id: str, version_id: str, *, exclude: str | None) -> None:
        for existing in self._jobs.list_jobs():
            if existing.job_id == exclude:
                continue
            if (
                existing.document_id == document_id
                and existing.version_id == version_id
                and existing.status in ACTIVE_JOB_STATUSES
            ):
                raise StoreError(
                    "job_active",
                    f"document {document_id} version {version_id} already has active job {existing.job_id} (status {existing.status}); cancel or wait for it first",
                    status_code=409,
                )

    # ----------------------------------------------------------- transitions

    def cancel_job(self, job_id: str) -> JobRecord:
        with self._dispatch_lock:
            job = self.get_job(job_id)
            if job.status in TERMINAL_JOB_STATUSES:
                return job
            self._write_cancel_request(job_id)
            if job_id in self._active:
                event = self._cancel_events.get(job_id)
                if event is not None:
                    event.set()
                self._jobs.append_event(job_id, "job_cancel_requested")
            else:
                self._finalize_cancel(job)
                return self.get_job(job_id)
        return self.get_job(job_id)

    def resume_job(self, job_id: str) -> JobRecord:
        with self._dispatch_lock:
            job = self.get_job(job_id)
            if job.status in ACTIVE_JOB_STATUSES:
                raise StoreError("job_active", f"job {job_id} is {job.status} and cannot be resumed", status_code=409)
            if job.status == "succeeded":
                raise StoreError(
                    "job_finished",
                    f"job {job_id} already succeeded; submit a new job to run the document again",
                    status_code=409,
                )
            self._reject_active_conflict(job.document_id, job.version_id, exclude=job_id)
            for stage in job.stages:
                if stage.status in ("running", "failed", "partial"):
                    stage.status = "pending"
                    stage.started_at = None
                    stage.completed_at = None
                    stage.error = None
            job.status = "queued"
            job.cancel_requested = False
            job.error = None
            job.completed_at = None
            self._remove_cancel_request(job_id)
            self._jobs.save(job)
            self._jobs.append_event(job_id, "job_resumed")
        self._enqueue(job_id)
        return self.get_job(job_id)

    # ---------------------------------------------------------------- reads

    def get_job(self, job_id: str) -> JobRecord:
        job = self._jobs.get(job_id)
        if job.status in ACTIVE_JOB_STATUSES and self._cancel_requested(job_id):
            job.cancel_requested = True
        return job

    def list_jobs(self) -> list[JobRecord]:
        jobs = self._jobs.list_jobs()
        for job in jobs:
            if job.status in ACTIVE_JOB_STATUSES and self._cancel_requested(job.job_id):
                job.cancel_requested = True
        return jobs

    def get_events(self, job_id: str, *, after: int = 0) -> dict[str, Any]:
        if after < 0:
            raise StoreError("invalid_cursor", "after must be a non-negative event sequence", status_code=422)
        self.get_job(job_id)
        events = self._jobs.read_events(job_id, after=after)
        next_cursor = max((int(event.get("seq") or 0) for event in events), default=after)
        return {"job_id": job_id, "after": after, "events": events, "next_cursor": next_cursor}

    # --------------------------------------------------------- cancel flags

    def _cancel_request_path(self, job_id: str) -> Path:
        return self._jobs.job_dir(job_id) / "cancel.flag"

    def _cancel_requested(self, job_id: str) -> bool:
        return self._cancel_request_path(job_id).exists()

    def _write_cancel_request(self, job_id: str) -> None:
        path = self._cancel_request_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def _remove_cancel_request(self, job_id: str) -> None:
        self._cancel_request_path(job_id).unlink(missing_ok=True)

    def _finalize_cancel(self, job: JobRecord) -> None:
        job.status = "cancelled"
        job.cancel_requested = False
        job.completed_at = utc_now()
        self._jobs.save(job)
        self._jobs.append_event(job.job_id, "job_cancelled")

    # ---------------------------------------------------------------- worker

    def _enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            self._dispatch(item)

    def _dispatch(self, job_id: str) -> None:
        with self._dispatch_lock:
            if self._stopping:
                return
            try:
                job = self._jobs.get(job_id)
            except StoreError:
                return
            if job.status != "queued":
                return
            if self._cancel_requested(job_id):
                self._finalize_cancel(job)
                return
            job.status = "running"
            if job.started_at is None:
                job.started_at = utc_now()
            self._jobs.save(job)
            self._jobs.append_event(job_id, "job_running")
            self._active.add(job_id)
            cancel_event = threading.Event()
            self._cancel_events[job_id] = cancel_event
        self._executor.attach_cancel_flag(job_id, cancel_event)
        try:
            self._executor.execute(self._jobs.get(job_id))
        except Exception as error:  # noqa: BLE001 - worker boundary must capture everything
            self._mark_worker_crash(job_id, error)
        finally:
            self._executor.detach_cancel_flag(job_id)
            with self._dispatch_lock:
                self._active.discard(job_id)
                self._cancel_events.pop(job_id, None)

    def _mark_worker_crash(self, job_id: str, error: Exception) -> None:
        try:
            job = self._jobs.get(job_id)
        except StoreError:
            return
        if job.status not in ACTIVE_JOB_STATUSES:
            return
        job.status = "failed"
        job.error = f"worker_crashed: {type(error).__name__}: {error}"
        job.completed_at = utc_now()
        self._jobs.save(job)
        self._jobs.append_event(job.job_id, "job_failed", message=job.error, data={"code": "worker_crashed"})
