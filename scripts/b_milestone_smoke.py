"""Milestone B end-to-end smoke against a running server (no provider key needed).

Flow: import document -> create job -> poll status -> verify failure path,
event cursor, subjects, text window, and curated run coexistence.
"""

from __future__ import annotations

import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
NOVEL_PATH = r"e:\project\agent\novel-cahracter-generator\tests\小说\斗罗大陆前20章.txt"


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


def main() -> None:
    text = open(NOVEL_PATH, encoding="utf-8", newline="").read()
    print(f"novel: {len(text)} code points")

    status, created = call("POST", "/v1/documents", {"display_name": "斗罗大陆·前20章", "text": text})
    assert status in (200, 201), created
    document_id = created["document_id"]
    version_id = created["version"]["version_id"]
    print(f"document: {document_id} version: {version_id} ({created['version']['code_points']} cp)")

    status, replay = call("POST", "/v1/documents", {"display_name": "重复上传", "text": text})
    assert status == 200 and replay["created"] is False, replay
    print("idempotent upload: ok")

    status, listed = call("GET", f"/v1/documents/{document_id}/versions")
    assert status == 200 and listed["versions"][0]["version_id"] == version_id
    print(f"versions listed: {len(listed['versions'])}")

    status, window = call("GET", f"/v1/documents/{document_id}/versions/{version_id}/text?start=0&end=12")
    assert status == 200 and window["offset_unit"] == "unicode_codepoint", window
    assert window["text"] == text[0:12]
    print(f"text window ok: {window['text']!r}")

    status, job_response = call("POST", f"/v1/documents/{document_id}/runs", {"version_id": version_id})
    assert status == 202, job_response
    job = job_response["job"]
    job_id = job["job_id"]
    print(f"job: {job_id} run: {job['run_id']} status: {job['status']}")

    status, duplicate = call("POST", f"/v1/documents/{document_id}/runs", {"version_id": version_id})
    assert status == 409 and duplicate["error"]["code"] == "job_active", duplicate
    print("duplicate submit rejected: ok")

    cursor = 0
    events_seen: list[str] = []
    terminal = False
    for _ in range(120):
        time.sleep(0.5)
        status, detail = call("GET", f"/v1/jobs/{job_id}")
        assert status == 200
        job = detail["job"]
        status_code, events = call("GET", f"/v1/jobs/{job_id}/events?after={cursor}")
        for event in events["events"]:
            events_seen.append(event["type"])
        cursor = events["next_cursor"]
        if job["status"] in ("succeeded", "partial", "failed", "cancelled"):
            terminal = True
            break
    assert terminal, f"job never reached terminal state: {job['status']}"
    assert job["status"] == "failed", job["status"]
    assert job["error"] and "provider_unconfigured" in job["error"], job["error"]
    failed_stage = next(stage for stage in job["stages"] if stage["status"] == "failed")
    print(f"job failed as expected: {failed_stage['stage_id']} ({failed_stage['error'][:80]}…)")
    print(f"events: {events_seen}")

    status, resumed = call("POST", f"/v1/jobs/{job_id}/resume")
    assert status == 200 and resumed["job"]["status"] == "queued", resumed
    print("resume accepted: job requeued")

    time.sleep(2.5)
    status, detail = call("GET", f"/v1/jobs/{job_id}")
    assert detail["job"]["status"] == "failed", detail["job"]["status"]
    print("resumed job failed again at same boundary (expected without provider key)")

    status, subjects = call("GET", f"/v1/documents/{document_id}/subjects")
    assert status == 200 and subjects["subjects"] == []
    print("subjects empty until a run publishes: ok")

    status, runs = call("GET", "/v1/runs")
    assert status == 200 and any(run["run_id"] == "douluo-20ch-dev13" for run in runs["runs"])
    print(f"curated runs intact: {[run['run_id'] for run in runs['runs']]}")

    status, jobs_list = call("GET", f"/v1/jobs?document_id={document_id}")
    assert status == 200 and len(jobs_list["jobs"]) >= 1
    print(f"jobs listed: {[item['job_id'] for item in jobs_list['jobs']]}")

    print("\nSMOKE OK: import -> job lifecycle -> failure path -> subjects -> curated coexistence")


if __name__ == "__main__":
    main()
