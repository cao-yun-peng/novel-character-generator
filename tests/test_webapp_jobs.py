"""Tests for the managed job service (R09): submit, cancel, resume, recovery."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from novel_character_generator.webapp.jobs import JobService, build_run_id, request_fingerprint, validated_pipeline
from novel_character_generator.webapp.store import (
    DocumentStore,
    JobRecord,
    JobStore,
    StoreError,
    SubjectIndex,
    utc_now,
)


def wait_until(predicate, *, timeout: float = 20.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class RecordingExecutor:
    """Pipeline test double: succeeds every pending stage, honors cancel events."""

    def __init__(self, hang_gates: dict[str, threading.Event] | None = None) -> None:
        self.executed: list[str] = []
        self.cancel_flags: dict[str, threading.Event] = {}
        self.hang_gates = hang_gates or {}
        self.job_store: JobStore | None = None

    def attach_cancel_flag(self, job_id: str, event: threading.Event) -> None:
        self.cancel_flags[job_id] = event

    def detach_cancel_flag(self, job_id: str) -> None:
        self.cancel_flags.pop(job_id, None)

    def execute(self, job: JobRecord) -> JobRecord:
        self.executed.append(job.job_id)
        gate = self.hang_gates.get(job.job_id)
        if gate is not None:
            gate.wait(timeout=30)
        if self.cancel_flags.get(job.job_id) is not None and self.cancel_flags[job.job_id].is_set():
            job.status = "cancelled"
            job.completed_at = utc_now()
            if self.job_store is not None:
                self.job_store.save(job)
                self.job_store.append_event(job.job_id, "job_cancelled")
        else:
            for stage in job.stages:
                if stage.status != "succeeded":
                    stage.status = "succeeded"
                    stage.completed_at = utc_now()
            job.status = "succeeded"
            job.completed_at = utc_now()
            if self.job_store is not None:
                self.job_store.save(job)
        return job


class Harness:
    def __init__(self, root: Path, executor: RecordingExecutor | None = None) -> None:
        self.root = root
        self.documents = DocumentStore(root)
        self.job_store = JobStore(root)
        self.subjects = SubjectIndex(self.documents)
        self.executor = executor or RecordingExecutor()
        self.executor.job_store = self.job_store
        self.service = JobService(
            document_store=self.documents,
            job_store=self.job_store,
            subject_index=self.subjects,
            executor=self.executor,
        )

    def add_document(self, text: str = "第一章\n李明走进房间。") -> str:
        version, _ = self.documents.create_version(text, display_name="测试小说")
        return version.version_id

    def stop(self) -> None:
        self.service.shutdown(timeout=5.0)


@pytest.fixture()
def harness(tmp_path: Path) -> Harness:
    instance = Harness(tmp_path)
    yield instance
    instance.stop()


def test_submit_job_runs_to_success(harness: Harness) -> None:
    version_id = harness.add_document()
    document_id = harness.documents.list_documents()[0].document_id
    job, created = harness.service.submit_job(document_id, version_id)
    assert created is True
    assert job.status == "queued"
    assert job.run_id.startswith("web-")  # non-ASCII display name falls back to "web" slug
    harness.service.start()
    assert wait_until(lambda: harness.service.get_job(job.job_id).status == "succeeded")
    assert harness.executor.executed == [job.job_id]
    events = harness.service.get_events(job.job_id)
    assert events["events"][0]["type"] == "job_created"
    assert events["next_cursor"] > 0


def test_run_id_slug_fallback_for_non_ascii() -> None:
    assert build_run_id("斗罗大陆", "job-abc123def456") == "web-abc123def456"
    assert build_run_id("Test Novel", "job-abc123def456") == "test-novel-abc123def456"


def test_idempotency_key_replays_same_job(harness: Harness) -> None:
    document = harness.documents.list_documents()[0] if harness.documents.list_documents() else None
    version_id = harness.add_document()
    document_id = harness.documents.list_documents()[0].document_id
    job, created = harness.service.submit_job(document_id, version_id, idempotency_key="key-1")
    assert created is True
    replay, created_again = harness.service.submit_job(document_id, version_id, idempotency_key="key-1")
    assert created_again is False
    assert replay.job_id == job.job_id


def test_idempotency_key_conflict_on_different_request(harness: Harness) -> None:
    version_id = harness.add_document()
    document_id = harness.documents.list_documents()[0].document_id
    harness.service.submit_job(document_id, version_id, idempotency_key="key-1")
    with pytest.raises(StoreError) as error:
        harness.service.submit_job(
            document_id, version_id,
            pipeline={"chunk_size": 9000},
            idempotency_key="key-1",
        )
    assert error.value.code == "idempotency_conflict"
    assert error.value.status_code == 409


def test_duplicate_active_job_rejected(harness: Harness) -> None:
    version_id = harness.add_document()
    document_id = harness.documents.list_documents()[0].document_id
    harness.service.submit_job(document_id, version_id)
    with pytest.raises(StoreError) as error:
        harness.service.submit_job(document_id, version_id)
    assert error.value.code == "job_active"
    assert error.value.status_code == 409


def test_cancel_queued_job_before_worker(harness: Harness) -> None:
    version_id = harness.add_document()
    document_id = harness.documents.list_documents()[0].document_id
    job, _ = harness.service.submit_job(document_id, version_id)
    cancelled = harness.service.cancel_job(job.job_id)
    assert cancelled.status == "cancelled"
    harness.service.start()
    time.sleep(0.1)
    assert harness.executor.executed == []
    assert harness.service.get_job(job.job_id).status == "cancelled"
    resumed = harness.service.resume_job(job.job_id)
    assert resumed.status == "queued"
    assert wait_until(lambda: harness.service.get_job(job.job_id).status == "succeeded")
    assert harness.executor.executed == [job.job_id]


def test_cancel_running_job_is_cooperative(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RecordingExecutor(hang_gates={}))
    try:
        version_id = harness.add_document()
        document_id = harness.documents.list_documents()[0].document_id
        job, _ = harness.service.submit_job(document_id, version_id)
        gate = threading.Event()
        harness.executor.hang_gates[job.job_id] = gate
        harness.service.start()
        assert wait_until(lambda: len(harness.executor.executed) == 1)
        requested = harness.service.cancel_job(job.job_id)
        assert requested.status == "running"
        assert requested.cancel_requested is True
        gate.set()
        assert wait_until(lambda: harness.service.get_job(job.job_id).status == "cancelled")
        events = [event["type"] for event in harness.service.get_events(job.job_id)["events"]]
        assert "job_cancel_requested" in events
        assert events[-1] == "job_cancelled"
    finally:
        harness.stop()


def test_resume_rejects_active_and_succeeded(harness: Harness) -> None:
    version_id = harness.add_document()
    document_id = harness.documents.list_documents()[0].document_id
    job, _ = harness.service.submit_job(document_id, version_id)
    with pytest.raises(StoreError) as error:
        harness.service.resume_job(job.job_id)
    assert error.value.code == "job_active"

    harness.service.start()
    assert wait_until(lambda: harness.service.get_job(job.job_id).status == "succeeded")
    with pytest.raises(StoreError) as error:
        harness.service.resume_job(job.job_id)
    assert error.value.code == "job_finished"


def test_resume_partial_or_failed_reruns(harness: Harness) -> None:
    version_id = harness.add_document()
    document_id = harness.documents.list_documents()[0].document_id
    job, _ = harness.service.submit_job(document_id, version_id)
    harness.service.start()
    assert wait_until(lambda: harness.service.get_job(job.job_id).status == "succeeded")

    stored = harness.job_store.get(job.job_id)
    stored.status = "failed"
    stored.stages[0].status = "failed"
    stored.stages[0].error = "boom"
    harness.job_store.save(stored)

    resumed = harness.service.resume_job(job.job_id)
    assert resumed.status == "queued"
    assert resumed.stages[0].status == "pending"
    assert wait_until(lambda: harness.service.get_job(job.job_id).status == "succeeded")
    assert harness.executor.executed == [job.job_id, job.job_id]


def test_events_cursor_is_incremental(harness: Harness) -> None:
    version_id = harness.add_document()
    document_id = harness.documents.list_documents()[0].document_id
    job, _ = harness.service.submit_job(document_id, version_id)
    first = harness.service.get_events(job.job_id)
    assert [event["type"] for event in first["events"]] == ["job_created"]
    second = harness.service.get_events(job.job_id, after=first["next_cursor"])
    assert second["events"] == []
    assert second["next_cursor"] == first["next_cursor"]
    with pytest.raises(StoreError) as error:
        harness.service.get_events(job.job_id, after=-1)
    assert error.value.code == "invalid_cursor"


def test_unknown_job_raises_404(harness: Harness) -> None:
    with pytest.raises(StoreError) as error:
        harness.service.get_job("job-000000000000")
    assert error.value.code == "job_not_found"
    assert error.value.status_code == 404


def test_startup_recovery_requeues_running_job(tmp_path: Path) -> None:
    version_id = Harness(tmp_path).add_document.__self__ if False else None  # placeholder
    documents = DocumentStore(tmp_path)
    job_store = JobStore(tmp_path)
    version, _ = documents.create_version("第一章\n李明走进房间。", display_name="测试小说")
    crashed = JobRecord(
        job_id=job_store.new_job_id(),
        run_id="web-crashed",
        document_id=version.document_id,
        version_id=version.version_id,
        document_hash=version.document_hash,
        display_name="测试小说",
        pipeline={},
    )
    crashed.status = "running"
    crashed.stages[0].status = "running"
    job_store.create(crashed)

    harness = Harness(tmp_path)
    try:
        recovered = harness.service.startup_recover()
        assert recovered == [crashed.job_id]
        state = harness.service.get_job(crashed.job_id)
        assert state.status == "queued"
        assert state.stages[0].status == "pending"
        harness.service.start()
        assert wait_until(lambda: harness.service.get_job(crashed.job_id).status == "succeeded")
        events = [event["type"] for event in harness.service.get_events(crashed.job_id)["events"]]
        assert "job_recovered" in events
    finally:
        harness.stop()


def test_startup_recovery_honors_cancel_flag(tmp_path: Path) -> None:
    documents = DocumentStore(tmp_path)
    job_store = JobStore(tmp_path)
    version, _ = documents.create_version("第一章\n李明走进房间。", display_name="测试小说")
    crashed = JobRecord(
        job_id=job_store.new_job_id(),
        run_id="web-crashed",
        document_id=version.document_id,
        version_id=version.version_id,
        document_hash=version.document_hash,
        display_name="测试小说",
        pipeline={},
    )
    crashed.status = "running"
    job_store.create(crashed)
    (job_store.job_dir(crashed.job_id) / "cancel.flag").touch()

    harness = Harness(tmp_path)
    try:
        assert harness.service.startup_recover() == []
        assert harness.service.get_job(crashed.job_id).status == "cancelled"
    finally:
        harness.stop()


def test_invalid_pipeline_config_rejected(harness: Harness) -> None:
    version_id = harness.add_document()
    document_id = harness.documents.list_documents()[0].document_id
    with pytest.raises(StoreError) as error:
        harness.service.submit_job(document_id, version_id, pipeline={"chunk_size": "big"})
    assert error.value.code == "invalid_pipeline_config"
    with pytest.raises(StoreError) as error:
        harness.service.submit_job(document_id, version_id, pipeline={"model": "x"})
    assert error.value.code == "invalid_pipeline_config"
    with pytest.raises(StoreError) as error:
        harness.service.submit_job(document_id, version_id, pipeline={"overlap_characters": -1})
    assert error.value.code == "invalid_pipeline_config"


def test_validated_pipeline_defaults_and_bounds() -> None:
    assert validated_pipeline(None) == {"chunk_size": 8000, "overlap_characters": 500}
    assert validated_pipeline({"chunk_size": 12000}) == {"chunk_size": 12000, "overlap_characters": 500}
    with pytest.raises(StoreError):
        validated_pipeline({"chunk_size": 10})
    with pytest.raises(StoreError):
        validated_pipeline({"overlap_characters": 99999})


def test_request_fingerprint_stable_and_sensitive() -> None:
    first = request_fingerprint("doc-a", "source-a", {"chunk_size": 8000})
    assert first == request_fingerprint("doc-a", "source-a", {"chunk_size": 8000})
    assert first != request_fingerprint("doc-a", "source-b", {"chunk_size": 8000})
    assert first != request_fingerprint("doc-a", "source-a", {"chunk_size": 9000})
