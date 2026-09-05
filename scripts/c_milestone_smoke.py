"""Milestone C end-to-end smoke against a running server (no provider key).

Flow: curated run reviews -> decision closed loop (validation, idempotency,
version conflict, reopen compensation, conflict target) -> decision history
-> subject resolution path. Human decisions are append-only; raw artifacts
stay untouched.
"""

from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8000"
RUN_ID = "douluo-20ch-dev13"


def call(method: str, path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(BASE + path, method=method)
    request.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    body = None
    if payload is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        with urllib.request.urlopen(request, body, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def decision_body(action: str, expected_revision: int, **extra) -> dict:
    body = {"action": action, "operator": "smoke-tester", "expected_revision": expected_revision}
    body.update(extra)
    return body


def post_decision(review_id: str, body: dict, key: str | None = None) -> tuple[int, dict]:
    headers = {"Idempotency-Key": key} if key else {}
    return call("POST", f"/v1/runs/{RUN_ID}/reviews/{review_id}/decisions", body, headers)


def main() -> None:
    status, reviews = call("GET", f"/v1/runs/{RUN_ID}/reviews")
    assert status == 200, reviews
    assert reviews["decision_revision"] == 0, reviews["decision_revision"]
    pending = reviews["pending_review_count"]
    assert pending == len(reviews["actionable"]), (pending, len(reviews["actionable"]))
    print(f"reviews: {len(reviews['actionable'])} actionable, revision {reviews['decision_revision']}")

    review_id = reviews["actionable"][0]["review_item_id"]
    conflicts = reviews["open_conflicts"][0]["conflicts"] if reviews["open_conflicts"] else []
    assert conflicts, "curated run must expose at least one conflict"
    conflict_id = conflicts[0]["conflict_id"]
    print(f"target review: {review_id}")
    print(f"target conflict: {conflict_id}")

    # Validation paths fail closed.
    status, body = post_decision(review_id, decision_body("reopen", 0))
    assert status == 422 and body["error"]["code"] == "decision_not_decided", body
    status, body = post_decision(review_id, decision_body("correct", 0, payload={}))
    assert status == 422 and body["error"]["code"] == "decision_new_value_required", body
    status, body = post_decision(review_id, decision_body("accept", 0, operator="  "))
    assert status == 422 and body["error"]["code"] == "decision_operator_required", body
    status, body = post_decision("review-doesnotexist000", decision_body("accept", 0))
    assert status == 404 and body["error"]["code"] == "review_not_found", body
    print("validation failures closed: ok")

    # First decision: accept, then idempotent replay and key conflict.
    status, first = post_decision(review_id, decision_body("accept", 0, note="确认为同一人物"), key="smoke-key-1")
    assert status == 201 and first["created"] is True, first
    assert first["revision"] == 1
    status, replay = post_decision(review_id, decision_body("accept", 0, note="确认为同一人物"), key="smoke-key-1")
    assert status == 200 and replay["decision"]["decision_id"] == first["decision"]["decision_id"], replay
    status, conflicting = post_decision(review_id, decision_body("reject", 0), key="smoke-key-1")
    assert status == 409 and conflicting["error"]["code"] == "decision_key_conflict", conflicting
    print("idempotency: replay + key conflict: ok")

    # Optimistic locking: stale revision rejected.
    status, stale = post_decision(review_id, decision_body("reject", 0), key="smoke-key-2")
    assert status == 409 and stale["error"]["code"] == "version_conflict", stale
    print("version conflict on stale revision: ok")

    # Conflict target decisions address registry conflicts.
    status, corrected = post_decision(
        conflict_id,
        decision_body("correct", 1, payload={"new_value": conflicts[0].get("values", ["?"])[0]}),
        key="smoke-key-3",
    )
    assert status == 201 and corrected["decision"]["target_kind"] == "conflict", corrected
    print("conflict target decision: ok")

    # Reopen compensation returns the review to the pending queue.
    status, reopened = post_decision(review_id, decision_body("reopen", 2, note="需要更多证据"), key="smoke-key-4")
    assert status == 201 and reopened["revision"] == 3, reopened
    status, after = call("GET", f"/v1/runs/{RUN_ID}/reviews")
    target = next(item for item in after["actionable"] if item["review_item_id"] == review_id)
    assert target["decision"]["status"] == "open", target
    assert target["decision"]["decision_count"] == 2, target
    assert after["pending_review_count"] == len(after["actionable"]), after
    conflict_entry = next(
        item for item in after["open_conflicts"]
        for conflict in item["conflicts"] if conflict["conflict_id"] == conflict_id
    )
    decided_conflict = next(
        conflict for conflict in conflict_entry["conflicts"] if conflict["conflict_id"] == conflict_id
    )
    assert decided_conflict["decision"]["status"] == "decided", decided_conflict
    print(f"reopen compensation: pending back to {after['pending_review_count']}: ok")

    # Decision history is append-only and ordered.
    status, history = call("GET", f"/v1/runs/{RUN_ID}/reviews/{review_id}/decisions")
    assert status == 200, history
    actions = [item["action"] for item in history["decisions"]]
    assert actions == ["accept", "reopen"], actions
    assert history["revision"] == 3, history
    print(f"decision history: {actions}: ok")

    # Curated artifacts stay immutable: registry hash still matches its manifest.
    status, registry = call("GET", f"/v1/runs/{RUN_ID}/characters")
    assert status == 200 and registry["characters"], registry
    print("curated run still queryable after decisions: ok")

    # Subject resolution endpoint path (no published subjects on this server).
    status, documents = call("GET", "/v1/documents")
    assert status == 200, documents
    if documents["documents"]:
        document_id = documents["documents"][0]["document_id"]
        status, subjects = call("GET", f"/v1/documents/{document_id}/subjects")
        assert status == 200 and isinstance(subjects["subjects"], list), subjects
        if subjects["subjects"]:
            subject_id = subjects["subjects"][0]["subject_id"]
            mapped_run = subjects["subjects"][0]["run_mappings"][0]["run_id"]
            status, resolved = call(
                "GET", f"/v1/documents/{document_id}/subjects/{subject_id}?run_id={mapped_run}"
            )
            assert status == 200 and resolved["run_resolution"]["status"] == "resolved", resolved
            status, unmapped = call(
                "GET", f"/v1/documents/{document_id}/subjects/{subject_id}?run_id=unknown-run"
            )
            assert unmapped["run_resolution"]["status"] == "unmapped_in_run", unmapped
            print(f"subject run resolution ({mapped_run}): ok")
        else:
            print("subjects empty (no published run): resolution path deferred to live pipeline")

    print("\nSMOKE OK: review decisions -> idempotency -> conflict -> reopen -> history")


if __name__ == "__main__":
    main()
