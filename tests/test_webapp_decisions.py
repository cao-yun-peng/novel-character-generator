"""Review decision closed-loop tests (R11) plus subject run resolution (R08)."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_character_generator.text import sha256_text
from novel_character_generator.webapp.app import create_app
from novel_character_generator.webapp.repository import RunRepository
from novel_character_generator.webapp.store import ReviewDecisionStore, StoreError

CURATED_TEXT = "唐三穿着灰衣。"
REVIEW_ID = "review-e0c61a90bdf59ea5e8af"
AUDIT_ID = "review-audit0000000000000ff"
CONFLICT_ID = "conflict-6a651986d83e113cf0c8"


def _write_curated_registry(base: Path) -> Path:
    curated = base / "curated"
    curated.mkdir(parents=True, exist_ok=True)
    input_path = curated / "input.txt"
    with input_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(CURATED_TEXT)
    document_hash = sha256_text(CURATED_TEXT)

    label_projection = {
        "document_hash": document_hash,
        "characters": [],
        "audit_items": [{
            "review_item_id": AUDIT_ID,
            "review_type": "ambiguous_label",
            "subject_character_id": "char-audit",
            "label_quote": "老者",
        }],
        "actionable_review_items": [{
            "review_item_id": REVIEW_ID,
            "review_type": "insufficient_identity_evidence",
            "subject_character_id": "char-actionable",
            "label_quote": "看门的青年",
            "reason_code": "insufficient_identity_evidence",
        }],
    }
    registry = {
        "document_hash": document_hash,
        "characters": [{
            "character_id": "char-actionable",
            "identity_status": "unresolved",
            "canonical_label": "看门的青年",
            "possible_conflicts": [{
                "conflict_id": CONFLICT_ID,
                "conflict_type": "multiple_values_same_attribute",
                "category": "clothing",
                "attribute": "长衫",
                "values": ["灰衣", "青衫"],
            }],
        }],
    }
    appearance_states = {
        "document_hash": document_hash,
        "state_segments": [],
        "transitions": [],
        "review": [],
    }
    payloads = {
        "registry": registry,
        "fact_groups": {"document_hash": document_hash},
        "appearance_states": appearance_states,
        "label_projection": label_projection,
    }
    artifacts: dict[str, dict[str, str]] = {}
    for name, payload in payloads.items():
        path = curated / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        artifacts[name] = {"path": f"curated/{name}.json", "sha256": sha256(path.read_bytes()).hexdigest()}
    registry_file = base / "curated-registry.json"
    registry_file.write_text(
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
    return registry_file


@pytest.fixture()
def client(tmp_path: Path) -> tuple[TestClient, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repository = RunRepository(
        _write_curated_registry(tmp_path),
        base_dir=tmp_path,
        managed_registry_file=workspace / "web-job-registry.json",
    )
    app = create_app(repository, workspace_root=workspace, job_service=_null_job_service(workspace))
    return TestClient(app), workspace


def _null_job_service(workspace: Path):
    """A job service whose worker never runs; only subject queries are needed."""
    from tests.test_webapp_jobs import Harness

    return Harness(workspace).service


def _submit(http: TestClient, review_id: str, body: dict, headers: dict | None = None) -> object:
    return http.post(
        f"/v1/runs/curated-run/reviews/{review_id}/decisions",
        json=body,
        headers=headers or {},
    )


def _accept_body(expected_revision: int, **overrides) -> dict:
    body = {
        "action": "accept",
        "operator": "alice",
        "note": "确认为同一人物",
        "expected_revision": expected_revision,
    }
    body.update(overrides)
    return body


# ------------------------------------------------------------------- store


def test_decision_store_append_and_revision(tmp_path: Path) -> None:
    store = ReviewDecisionStore(tmp_path)
    assert store.current_revision("curated-run") == 0
    assert store.list_decisions("curated-run") == []

    decision, created = store.submit(
        "curated-run",
        review_id=REVIEW_ID,
        target_kind="review",
        action="accept",
        operator="alice",
        note="",
        payload={},
        expected_revision=0,
        idempotency_key=None,
    )
    assert created is True
    assert decision.revision == 1
    assert decision.decision_id.startswith("decision-")
    assert store.current_revision("curated-run") == 1

    # Reload from disk in a fresh instance: append-only log survives.
    reloaded = ReviewDecisionStore(tmp_path)
    assert [item.decision_id for item in reloaded.list_decisions("curated-run")] == [decision.decision_id]
    assert reloaded.current_revision("curated-run") == 1


def test_decision_store_version_conflict(tmp_path: Path) -> None:
    store = ReviewDecisionStore(tmp_path)
    store.submit("curated-run", review_id=REVIEW_ID, target_kind="review", action="accept",
                 operator="alice", note="", payload={}, expected_revision=0, idempotency_key=None)
    with pytest.raises(StoreError) as error:
        store.submit("curated-run", review_id=REVIEW_ID, target_kind="review", action="reject",
                     operator="bob", note="", payload={}, expected_revision=0, idempotency_key=None)
    assert error.value.code == "version_conflict"
    assert error.value.status_code == 409
    assert store.current_revision("curated-run") == 1


def test_decision_store_idempotency(tmp_path: Path) -> None:
    store = ReviewDecisionStore(tmp_path)
    first, created = store.submit("curated-run", review_id=REVIEW_ID, target_kind="review", action="accept",
                                  operator="alice", note="", payload={"basis": "q"}, expected_revision=0,
                                  idempotency_key="key-1")
    assert created is True

    replay, created = store.submit("curated-run", review_id=REVIEW_ID, target_kind="review", action="accept",
                                   operator="alice", note="", payload={"basis": "q"}, expected_revision=0,
                                   idempotency_key="key-1")
    assert created is False
    assert replay.decision_id == first.decision_id
    assert store.current_revision("curated-run") == 1

    with pytest.raises(StoreError) as error:
        store.submit("curated-run", review_id=REVIEW_ID, target_kind="review", action="reject",
                     operator="alice", note="", payload={"basis": "q"}, expected_revision=0,
                     idempotency_key="key-1")
    assert error.value.code == "decision_key_conflict"


def test_decision_store_input_validation(tmp_path: Path) -> None:
    store = ReviewDecisionStore(tmp_path)
    with pytest.raises(StoreError) as error:
        store.submit("curated-run", review_id=REVIEW_ID, target_kind="review", action="merge",
                     operator="alice", note="", payload={}, expected_revision=0, idempotency_key=None)
    assert error.value.code == "decision_action_invalid"

    with pytest.raises(StoreError) as error:
        store.submit("curated-run", review_id=REVIEW_ID, target_kind="review", action="accept",
                     operator="  ", note="", payload={}, expected_revision=0, idempotency_key=None)
    assert error.value.code == "decision_operator_required"

    with pytest.raises(StoreError) as error:
        store.current_revision("../escape")
    assert error.value.code == "run_id_invalid"


# ---------------------------------------------------------------- service


def test_submit_decision_and_history(client) -> None:
    http, _ = client
    response = _submit(http, REVIEW_ID, _accept_body(0))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert body["decision"]["action"] == "accept"
    assert body["decision"]["target_kind"] == "review"
    assert body["revision"] == 1

    history = http.get(f"/v1/runs/curated-run/reviews/{REVIEW_ID}/decisions")
    assert history.status_code == 200
    assert [item["action"] for item in history.json()["decisions"]] == ["accept"]
    assert history.json()["revision"] == 1

    reviews = http.get("/v1/runs/curated-run/reviews").json()
    actionable = reviews["actionable"][0]
    assert actionable["decision"]["status"] == "decided"
    assert actionable["decision"]["latest_action"] == "accept"
    assert reviews["decision_revision"] == 1
    assert reviews["pending_review_count"] == 0


def test_submit_decision_rejects_unknown_review(client) -> None:
    http, _ = client
    response = _submit(http, "review-doesnotexist00", _accept_body(0))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "review_not_found"

    unknown_run = http.post(
        "/v1/runs/no-such-run/reviews/whatever/decisions",
        json=_accept_body(0),
    )
    assert unknown_run.status_code == 404
    assert unknown_run.json()["error"]["code"] == "run_not_found"


def test_submit_decision_correct_requires_new_value(client) -> None:
    http, _ = client
    response = _submit(http, REVIEW_ID, _accept_body(0, action="correct", payload={"note_only": "x"}))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "decision_new_value_required"

    corrected = _submit(http, REVIEW_ID, _accept_body(
        0, action="correct", payload={"new_value": "青衫老者", "basis_quote": "青衫"},
    ))
    assert corrected.status_code == 201
    assert corrected.json()["decision"]["payload"]["new_value"] == "青衫老者"


def test_reopen_requires_prior_decision_and_reopens(client) -> None:
    http, _ = client
    naive = _submit(http, REVIEW_ID, _accept_body(0, action="reopen"))
    assert naive.status_code == 422
    assert naive.json()["error"]["code"] == "decision_not_decided"

    assert _submit(http, REVIEW_ID, _accept_body(0)).status_code == 201
    reopened = _submit(http, REVIEW_ID, _accept_body(1, action="reopen", note="需要更多证据"))
    assert reopened.status_code == 201

    reviews = http.get("/v1/runs/curated-run/reviews").json()
    decision = reviews["actionable"][0]["decision"]
    assert decision["status"] == "open"
    assert decision["decision_count"] == 2
    assert reviews["pending_review_count"] == 1

    history = http.get(f"/v1/runs/curated-run/reviews/{REVIEW_ID}/decisions").json()
    assert [item["action"] for item in history["decisions"]] == ["accept", "reopen"]


def test_decision_target_conflict(client) -> None:
    http, _ = client
    response = _submit(http, CONFLICT_ID, _accept_body(0, action="correct",
                                                       payload={"new_value": "灰衣"}))
    assert response.status_code == 201, response.text
    assert response.json()["decision"]["target_kind"] == "conflict"

    reviews = http.get("/v1/runs/curated-run/reviews").json()
    conflict = reviews["open_conflicts"][0]["conflicts"][0]
    assert conflict["decision"]["status"] == "decided"


def test_decision_http_version_conflict_and_idempotency(client) -> None:
    http, _ = client
    first = _submit(http, REVIEW_ID, _accept_body(0), headers={"Idempotency-Key": "dec-1"})
    assert first.status_code == 201

    stale = _submit(http, REVIEW_ID, _accept_body(0), headers={"Idempotency-Key": "dec-2"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"

    replay = _submit(http, REVIEW_ID, _accept_body(0), headers={"Idempotency-Key": "dec-1"})
    assert replay.status_code == 200
    assert replay.json()["decision"]["decision_id"] == first.json()["decision"]["decision_id"]

    different = _submit(
        http, REVIEW_ID,
        _accept_body(0, action="reject"),
        headers={"Idempotency-Key": "dec-1"},
    )
    assert different.status_code == 409
    assert different.json()["error"]["code"] == "decision_key_conflict"


def test_reviews_view_undecided_defaults(client) -> None:
    http, _ = client
    reviews = http.get("/v1/runs/curated-run/reviews").json()
    assert reviews["decision_revision"] == 0
    assert reviews["pending_review_count"] == 1
    assert "decision" not in reviews["actionable"][0]


# ------------------------------------------------------- subject resolution


def test_subject_run_resolution(client) -> None:
    http, workspace = client
    created = http.post("/v1/documents", json={"display_name": "测试", "text": "正文"}).json()
    document_id = created["document_id"]

    from tests.test_webapp_jobs import Harness

    harness = Harness(workspace)
    harness.subjects.record_run(document_id, "curated-run", [
        {"character_id": "char-actionable", "canonical_label": "看门的青年"},
    ])
    subjects = http.get(f"/v1/documents/{document_id}/subjects").json()["subjects"]
    subject_id = subjects[0]["subject_id"]

    resolved = http.get(
        f"/v1/documents/{document_id}/subjects/{subject_id}",
        params={"run_id": "curated-run"},
    ).json()
    assert resolved["run_resolution"] == {
        "run_id": "curated-run",
        "status": "resolved",
        "character_id": "char-actionable",
    }

    unmapped = http.get(
        f"/v1/documents/{document_id}/subjects/{subject_id}",
        params={"run_id": "another-run"},
    ).json()
    assert unmapped["run_resolution"]["status"] == "unmapped_in_run"
    assert unmapped["run_resolution"]["character_id"] is None

    bare = http.get(f"/v1/documents/{document_id}/subjects/{subject_id}").json()
    assert bare["run_resolution"] is None
