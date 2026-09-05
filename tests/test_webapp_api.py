"""HTTP API tests for managed documents, jobs, subjects, and text windows."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_character_generator.text import sha256_text
from novel_character_generator.webapp.app import create_app
from novel_character_generator.webapp.repository import RunRepository
from tests.test_webapp_jobs import Harness, wait_until

CURATED_TEXT = "唐三穿着灰衣。"


def _write_curated_registry(base: Path) -> Path:
    curated = base / "curated"
    curated.mkdir(parents=True, exist_ok=True)
    input_path = curated / "input.txt"
    with input_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(CURATED_TEXT)
    document_hash = sha256_text(CURATED_TEXT)
    artifacts: dict[str, dict[str, str]] = {}
    for name in ("registry", "fact_groups", "appearance_states", "label_projection"):
        path = curated / f"{name}.json"
        path.write_text(json.dumps({"document_hash": document_hash}), encoding="utf-8")
        artifacts[name] = {"path": f"curated/{name}.json", "sha256": sha256(path.read_bytes()).hexdigest()}
    registry = base / "curated-registry.json"
    registry.write_text(
        json.dumps({
            "schema_version": "web-run-registry-v1",
            "runs": [{
                "run_id": "curated-run",
                "display_name": "Curated",
                "input_file": "curated/input.txt",
                "document_hash": document_hash,
                "source_document_version_id": "source-" + document_hash[:16],
                "snapshot_namespace": "curated-snapshot",
                "artifacts": artifacts,
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry


@pytest.fixture()
def client(tmp_path: Path) -> tuple[TestClient, Harness]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    harness = Harness(workspace)
    repository = RunRepository(
        _write_curated_registry(tmp_path),
        base_dir=tmp_path,
        managed_registry_file=workspace / "web-job-registry.json",
    )
    app = create_app(repository, workspace_root=workspace, job_service=harness.service)
    # No `with` block: lifespan (worker thread) intentionally stays off; the
    # job endpoints under test only need the service, not execution.
    return TestClient(app), harness


def _upload(client: TestClient, text: str, display_name: str = "测试小说") -> dict:
    response = client.post("/v1/documents", json={"display_name": display_name, "text": text})
    assert response.status_code == 201, response.text
    return response.json()


def test_document_upload_is_content_addressed(client) -> None:
    http, _ = client
    first = _upload(http, "第一章\n李明走进房间。")
    assert first["created"] is True
    assert first["version"]["code_points"] == 11

    second = http.post("/v1/documents", json={"display_name": "另一个名字", "text": "第一章\n李明走进房间。"})
    assert second.status_code == 200
    body = second.json()
    assert body["created"] is False
    assert body["document_id"] == first["document_id"]
    assert body["version"]["version_id"] == first["version"]["version_id"]
    # display_name stays bound to the first upload
    assert body["display_name"] == "测试小说"

    empty = http.post("/v1/documents", json={"display_name": "空", "text": ""})
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "document_empty"


def test_document_listing_and_versions(client) -> None:
    http, _ = client
    created = _upload(http, "正文一")
    document_id = created["document_id"]

    listed = http.get("/v1/documents")
    assert listed.status_code == 200
    documents = listed.json()["documents"]
    assert [item["document_id"] for item in documents] == [document_id]
    assert documents[0]["latest_version_id"] == created["version"]["version_id"]

    versions = http.get(f"/v1/documents/{document_id}/versions")
    assert versions.status_code == 200
    assert [item["version_id"] for item in versions.json()["versions"]] == [created["version"]["version_id"]]

    missing = http.get("/v1/documents/doc-000000000000/versions")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "document_not_found"


def test_create_run_and_idempotency_header(client) -> None:
    http, _ = client
    created = _upload(http, "第一章\n李明走进房间。")
    document_id = created["document_id"]
    version_id = created["version"]["version_id"]

    response = http.post(
        f"/v1/documents/{document_id}/runs",
        json={"version_id": version_id, "pipeline": {"chunk_size": 8000}},
        headers={"Idempotency-Key": "run-key-1"},
    )
    assert response.status_code == 202, response.text
    job = response.json()["job"]
    assert job["status"] == "queued"
    assert job["run_id"]
    assert job["stages"][0]["stage_id"] == "m1"

    replay = http.post(
        f"/v1/documents/{document_id}/runs",
        json={"version_id": version_id, "pipeline": {"chunk_size": 8000}},
        headers={"Idempotency-Key": "run-key-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["job"]["job_id"] == job["job_id"]

    conflict = http.post(
        f"/v1/documents/{document_id}/runs",
        json={"version_id": version_id, "pipeline": {"chunk_size": 9000}},
        headers={"Idempotency-Key": "run-key-1"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"

    duplicate = http.post(f"/v1/documents/{document_id}/runs", json={"version_id": version_id})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "job_active"

    bad_pipeline = http.post(f"/v1/documents/{document_id}/runs", json={"pipeline": {"model": "x"}})
    assert bad_pipeline.status_code == 422
    assert bad_pipeline.json()["error"]["code"] == "invalid_pipeline_config"


def test_job_detail_events_cancel_resume(client) -> None:
    http, harness = client
    created = _upload(http, "第一章\n李明走进房间。")
    document_id = created["document_id"]
    job = http.post(f"/v1/documents/{document_id}/runs", json={}).json()["job"]
    job_id = job["job_id"]

    detail = http.get(f"/v1/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["job"]["job_id"] == job_id

    events = http.get(f"/v1/jobs/{job_id}/events")
    assert events.status_code == 200
    first = events.json()
    assert [event["type"] for event in first["events"]] == ["job_created"]
    assert first["next_cursor"] == 1

    incremental = http.get(f"/v1/jobs/{job_id}/events", params={"after": first["next_cursor"]})
    assert incremental.json()["events"] == []
    assert incremental.json()["next_cursor"] == first["next_cursor"]

    cancelled = http.post(f"/v1/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"
    # cancel is idempotent
    assert http.post(f"/v1/jobs/{job_id}/cancel").json()["job"]["status"] == "cancelled"

    resumed = http.post(f"/v1/jobs/{job_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["job"]["status"] == "queued"

    assert http.get("/v1/jobs/job-000000000000").status_code == 404
    assert http.get("/v1/jobs").json()["jobs"][0]["job_id"] == job_id
    filtered = http.get("/v1/jobs", params={"document_id": "doc-000000000000"})
    assert filtered.json()["jobs"] == []


def test_job_lifecycle_runsthrough_worker(client) -> None:
    http, harness = client
    created = _upload(http, "第一章\n李明走进房间。")
    document_id = created["document_id"]
    job = http.post(f"/v1/documents/{document_id}/runs", json={}).json()["job"]

    harness.service.start()
    finished = wait_until(
        lambda: http.get(f"/v1/jobs/{job['job_id']}").json()["job"]["status"] == "succeeded"
    )
    assert finished
    event_types = [event["type"] for event in http.get(f"/v1/jobs/{job['job_id']}/events").json()["events"]]
    assert "job_running" in event_types


def test_subjects_endpoints(client) -> None:
    http, harness = client
    created = _upload(http, "第一章\n李明走进房间。")
    document_id = created["document_id"]
    harness.subjects.record_run(document_id, "managed-run-1", [
        {"character_id": "char-lee", "canonical_label": "李明"},
    ])

    listed = http.get(f"/v1/documents/{document_id}/subjects")
    assert listed.status_code == 200
    subjects = listed.json()["subjects"]
    assert len(subjects) == 1
    assert subjects[0]["preferred_label"] == "李明"
    assert subjects[0]["run_mappings"][0]["run_id"] == "managed-run-1"
    subject_id = subjects[0]["subject_id"]

    detail = http.get(f"/v1/documents/{document_id}/subjects/{subject_id}")
    assert detail.status_code == 200
    assert detail.json()["subject"]["subject_id"] == subject_id

    assert http.get(f"/v1/documents/{document_id}/subjects/subj-000000000000").status_code == 404
    assert http.get("/v1/documents/doc-000000000000/subjects").status_code == 404


def test_version_text_window_contract(client) -> None:
    http, _ = client
    text = "唐三穿着灰衣。\r\n他笑了😀。\n𠮷字测试。"
    created = _upload(http, text)
    document_id = created["document_id"]
    version_id = created["version"]["version_id"]

    response = http.get(
        f"/v1/documents/{document_id}/versions/{version_id}/text",
        params={"start": 0, "end": 7},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["offset_unit"] == "unicode_codepoint"
    assert body["total_code_points"] == len(text)
    assert body["text"] == text[0:7]

    invalid = http.get(
        f"/v1/documents/{document_id}/versions/{version_id}/text",
        params={"start": -1, "end": 3},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_range"

    unknown_version = http.get(
        f"/v1/documents/{document_id}/versions/source-0000000000000000/text",
        params={"start": 0, "end": 3},
    )
    assert unknown_version.status_code == 404
    assert unknown_version.json()["error"]["code"] == "version_not_found"


def test_managed_registry_reload_merges_runs(tmp_path: Path) -> None:
    curated_registry = _write_curated_registry(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    managed = workspace / "web-job-registry.json"
    artifacts_dir = tmp_path / "managed-artifacts"
    artifacts_dir.mkdir()

    def write_managed_run(run_id: str) -> None:
        existing: list[dict] = []
        if managed.is_file():
            existing = list(json.loads(managed.read_text(encoding="utf-8")).get("runs", []))
        artifacts: dict[str, dict[str, str]] = {}
        text = "新的正文"
        for name in ("registry", "fact_groups", "appearance_states", "label_projection", "document_evidence"):
            path = artifacts_dir / f"{run_id}-{name}.json"
            path.write_text(json.dumps({"document_hash": sha256_text(text)}), encoding="utf-8")
            artifacts[name] = {
                "path": f"managed-artifacts/{path.name}",
                "sha256": sha256(path.read_bytes()).hexdigest(),
            }
        existing.append({
            "run_id": run_id,
            "display_name": run_id,
            "input_file": "curated/input.txt",
            "document_hash": sha256_text(CURATED_TEXT),
            "source_document_version_id": "source-" + sha256_text(CURATED_TEXT)[:16],
            "snapshot_namespace": run_id,
            "artifacts": artifacts,
        })
        managed.write_text(
            json.dumps({"schema_version": "web-run-registry-v1", "runs": existing}, ensure_ascii=False),
            encoding="utf-8",
        )

    repository = RunRepository(
        curated_registry,
        base_dir=tmp_path,
        managed_registry_file=managed,
    )
    assert [spec.run_id for spec in repository.list_runs()] == ["curated-run"]

    write_managed_run("managed-run-a")
    assert [spec.run_id for spec in repository.list_runs()] == ["curated-run"]  # no reload yet
    repository.reload()
    assert [spec.run_id for spec in repository.list_runs()] == ["curated-run", "managed-run-a"]

    write_managed_run("managed-run-b")
    repository.reload()
    assert [spec.run_id for spec in repository.list_runs()] == ["curated-run", "managed-run-a", "managed-run-b"]

    spec = repository.get_run("managed-run-b")
    assert spec.artifacts["document_evidence"].path.is_file()
