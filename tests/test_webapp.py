"""Webapp read-only service and API tests.

Synthetic fixtures cover the repository fail-closed contract and the
unicode code point window contract (CRLF, emoji, extended hanzi,
combining marks, duplicate quotes). Real-run tests reproduce the four
saved dev29 snapshots byte-for-byte via snapshot_id and are skipped when
the curated run directory is absent.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_character_generator.webapp.app import create_app
from novel_character_generator.webapp.repository import RunRepository, WebRunError, read_utf8_text, sha256_text

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_REGISTRY = REPO_ROOT / "runs" / "web-run-registry.json"
REAL_RUN_ID = "douluo-20ch-dev13"
SAVED_SNAPSHOTS = REPO_ROOT / "runs/douluo-20ch-e2e-dev13-20260831/snapshots-dev29/character-snapshots.json"

SYNTHETIC_TEXT = (
    "第一段：唐三穿着一身灰衣。\r\n"
    "第二段：他开心地笑了😀一下。\r\n"
    "第三段：𠮷是一个扩展区汉字。\n"
    "第四段：cafe\u0301 上有组合字符。\n"
    "重复引文：一身灰衣。又见一身灰衣。\n"
)

SYNTHETIC_DOC_HASH = sha256_text(SYNTHETIC_TEXT)


def _write_registry(base: Path, *, document_hash: str, artifact_hashes: dict[str, str] | None = None,
                    run_id: str = "synthetic-run") -> Path:
    syn = base / "synthetic"
    syn.mkdir(exist_ok=True)
    artifacts = {}
    for name in ("registry", "fact_groups", "appearance_states", "label_projection"):
        artifact_path = syn / f"{name}.json"
        artifact_path.write_text(json.dumps({"document_hash": document_hash}), encoding="utf-8")
        digest = sha256(artifact_path.read_bytes()).hexdigest()
        if artifact_hashes and name in artifact_hashes:
            digest = artifact_hashes[name]
        artifacts[name] = {"path": f"synthetic/{name}.json", "sha256": digest}
    registry = {
        "schema_version": "web-run-registry-v1",
        "runs": [{
            "run_id": run_id,
            "display_name": "Synthetic coordinate corpus",
            "input_file": "synthetic/input.txt",
            "document_hash": document_hash,
            "source_document_version_id": "source-" + document_hash[:16],
            "snapshot_namespace": "synthetic-snapshot",
            "artifacts": artifacts,
        }],
    }
    registry_path = base / "web-run-registry.json"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry_path


def _make_synthetic_app(tmp_path: Path, *, document_hash: str = SYNTHETIC_DOC_HASH,
                        artifact_hashes: dict[str, str] | None = None, run_id: str = "synthetic-run") -> TestClient:
    syn = tmp_path / "synthetic"
    syn.mkdir()
    input_path = syn / "input.txt"
    with input_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(SYNTHETIC_TEXT)
    registry_path = _write_registry(tmp_path, document_hash=document_hash, artifact_hashes=artifact_hashes, run_id=run_id)
    app = create_app(RunRepository(registry_path, base_dir=tmp_path))
    return TestClient(app)


def _real_app() -> TestClient | None:
    if not REAL_REGISTRY.is_file() or not SAVED_SNAPSHOTS.is_file():
        return None
    try:
        repository = RunRepository(REAL_REGISTRY)
    except WebRunError:
        return None
    return TestClient(create_app(repository))


# ------------------------------------------------------------ repository


def test_repository_rejects_artifact_hash_mismatch(tmp_path: Path) -> None:
    client = _make_synthetic_app(tmp_path, artifact_hashes={"registry": "0" * 64})
    response = client.get("/v1/runs/synthetic-run/characters")
    assert response.status_code == 500
    payload = response.json()
    assert payload["error"]["code"] == "artifact_hash_mismatch"


def test_repository_rejects_document_hash_mismatch(tmp_path: Path) -> None:
    client = _make_synthetic_app(tmp_path, document_hash="1" * 64)
    response = client.get("/v1/runs/synthetic-run/text", params={"start": 0, "end": 5})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "document_hash_mismatch"


def test_repository_rejects_duplicate_run_ids(tmp_path: Path) -> None:
    syn = tmp_path / "synthetic"
    syn.mkdir()
    (syn / "input.txt").write_text("正文", encoding="utf-8")
    digest = sha256_text("正文")
    _write_registry(tmp_path, document_hash=digest, run_id="dup")
    registry_path = tmp_path / "web-run-registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["runs"].append(dict(payload["runs"][0]))
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WebRunError) as error:
        RunRepository(registry_path, base_dir=tmp_path)
    assert error.value.code == "registry_invalid"


def test_repository_rejects_unknown_schema(tmp_path: Path) -> None:
    registry_path = tmp_path / "web-run-registry.json"
    registry_path.write_text(json.dumps({"schema_version": "other"}), encoding="utf-8")
    with pytest.raises(WebRunError) as error:
        RunRepository(registry_path, base_dir=tmp_path)
    assert error.value.code == "registry_invalid"


# ------------------------------------------------- code point window contract


def test_text_window_uses_unicode_code_points(tmp_path: Path) -> None:
    client = _make_synthetic_app(tmp_path)
    response = client.get("/v1/runs/synthetic-run/text", params={"start": 0, "end": len(SYNTHETIC_TEXT)})
    assert response.status_code == 200
    payload = response.json()
    assert payload["offset_unit"] == "unicode_codepoint"
    assert payload["total_code_points"] == len(SYNTHETIC_TEXT)
    assert payload["text"] == SYNTHETIC_TEXT
    assert payload["document_hash"] == SYNTHETIC_DOC_HASH


def test_text_window_preserves_crlf_and_supplementary_planes(tmp_path: Path) -> None:
    client = _make_synthetic_app(tmp_path)
    crlf_index = SYNTHETIC_TEXT.index("\r\n")
    response = client.get("/v1/runs/synthetic-run/text", params={"start": crlf_index, "end": crlf_index + 2})
    assert response.json()["text"] == "\r\n"

    emoji_index = SYNTHETIC_TEXT.index("\U0001f600")
    response = client.get("/v1/runs/synthetic-run/text", params={"start": emoji_index, "end": emoji_index + 1})
    assert response.json()["text"] == "\U0001f600"

    hanzi_index = SYNTHETIC_TEXT.index("\U00020bb7")
    response = client.get("/v1/runs/synthetic-run/text", params={"start": hanzi_index, "end": hanzi_index + 1})
    assert response.json()["text"] == "\U00020bb7"

    combining_index = SYNTHETIC_TEXT.index("e\u0301")
    response = client.get("/v1/runs/synthetic-run/text", params={"start": combining_index, "end": combining_index + 3})
    assert response.json()["text"] == "e\u0301 "


def test_text_window_rejects_invalid_ranges(tmp_path: Path) -> None:
    client = _make_synthetic_app(tmp_path)
    for start, end in ((-1, 5), (5, 5), (10, 5), (0, len(SYNTHETIC_TEXT) + 1), (0, 10001)):
        response = client.get("/v1/runs/synthetic-run/text", params={"start": start, "end": end})
        assert response.status_code == 422, (start, end)
        assert response.json()["error"]["code"] == "invalid_range"


def test_api_error_envelope_shape(tmp_path: Path) -> None:
    client = _make_synthetic_app(tmp_path)
    response = client.get("/v1/runs/nope/characters")
    assert response.status_code == 404
    payload = response.json()
    assert payload["schema_version"] == "web-api-v1"
    assert payload["request_id"].startswith("req-")
    assert payload["error"]["code"] == "run_not_found"
    assert payload["error"]["retryable"] is False
    assert response.headers["X-Request-Id"] == payload["request_id"]


# ------------------------------------------------------------- real run


@pytest.fixture(scope="module")
def real_client() -> TestClient:
    client = _real_app()
    if client is None:
        pytest.skip("curated douluo run artifacts are not present")
    return client


def test_real_runs_listed(real_client: TestClient) -> None:
    payload = real_client.get("/v1/runs").json()
    run_ids = [run["run_id"] for run in payload["runs"]]
    assert REAL_RUN_ID in run_ids


def test_real_characters_projection(real_client: TestClient) -> None:
    payload = real_client.get(f"/v1/runs/{REAL_RUN_ID}/characters").json()
    characters = {entry["character_id"]: entry for entry in payload["characters"]}
    assert len(characters) >= 7
    suytao = characters["char-431fd9f3afcbe1cece75"]
    assert suytao["canonical_label"] == "素云涛"
    label_kinds = {label["label_quote"]: label["label_kind"] for label in suytao["labels"]}
    assert label_kinds["素云涛"] == "proper_name"
    assert label_kinds["战魂大师"] == "title"
    watcher = characters["char-29c8430a024fab728208"]
    assert watcher["actionable_review_count"] == 1
    assert watcher["canonical_label"] == "看门的青年"


def test_real_character_states(real_client: TestClient) -> None:
    payload = real_client.get(
        f"/v1/runs/{REAL_RUN_ID}/characters/char-431fd9f3afcbe1cece75/states"
    ).json()
    segments = payload["state_segments"]
    assert segments, "expected at least one state segment"
    sequence = [segment["sequence_index"] for segment in segments]
    assert sequence == sorted(sequence)
    transitions = payload["transitions"]
    assert any(transition["dimension"] == "form" for transition in transitions)
    assert payload["offset_unit"] == "unicode_codepoint"


def test_real_snapshot_matches_reference_and_saved_counts(real_client: TestClient) -> None:
    from novel_character_generator.character_snapshot import build_character_snapshot
    from novel_character_generator.webapp.app import DEFAULT_REGISTRY_FILE
    from novel_character_generator.webapp.repository import RunRepository

    saved = json.loads(SAVED_SNAPSHOTS.read_text(encoding="utf-8"))
    assert len(saved) == 4
    repository = RunRepository(DEFAULT_REGISTRY_FILE)
    spec = repository.get_run(REAL_RUN_ID)
    document_text = repository.load_document_text(spec)
    inputs = {name: repository.load_artifact(spec, name) for name in ("fact_groups", "appearance_states", "label_projection")}
    for expected in saved:
        selector = expected["selector"]
        params = {"position": selector["document_position"]}
        for key in ("life_stage", "form_state", "scene_state"):
            if selector[key] != "unknown":
                params[key] = selector[key]
        response = real_client.get(
            f"/v1/runs/{REAL_RUN_ID}/characters/{expected['character_id']}/snapshot/explain",
            params=params,
        )
        assert response.status_code == 200, expected["character_id"]
        snapshot = response.json()
        reference = build_character_snapshot(
            document_text=document_text,
            fact_groups=inputs["fact_groups"],
            appearance_states=inputs["appearance_states"],
            label_projection=inputs["label_projection"],
            run_id=spec.snapshot_namespace,
            character_id=expected["character_id"],
            document_position=selector["document_position"],
            life_stage=selector["life_stage"] if selector["life_stage"] != "unknown" else None,
            form_state=selector["form_state"] if selector["form_state"] != "unknown" else None,
            scene_state=selector["scene_state"] if selector["scene_state"] != "unknown" else None,
            explain=True,
        )
        assert snapshot["snapshot_id"] == reference["snapshot_id"], selector
        assert snapshot["artifact_set_id"] == reference["artifact_set_id"]
        assert snapshot["run_id"] == "douluo-snapshot-dev29"
        assert len(snapshot["active_traits"]) == len(expected["active_traits"]), selector
        assert len(snapshot["provisional_traits"]) == len(expected["provisional_traits"]), selector
        assert len(snapshot["excluded_facts"]) == len(expected["excluded_facts"]), selector


def test_real_snapshot_unknown_character_is_404(real_client: TestClient) -> None:
    response = real_client.get(
        f"/v1/runs/{REAL_RUN_ID}/characters/char-does-not-exist/snapshot", params={"position": 100}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "character_not_found"


def test_real_text_window_matches_source_file(real_client: TestClient) -> None:
    source = read_utf8_text(REPO_ROOT / "tests/小说/斗罗大陆前20章.txt")
    assert len(source) == 38251
    for start, end in ((0, 500), (206, 260), (38000, 38251)):
        payload = real_client.get(
            f"/v1/runs/{REAL_RUN_ID}/text", params={"start": start, "end": end}
        ).json()
        assert payload["total_code_points"] == len(source)
        assert payload["text"] == source[start:end]


def test_real_reviews(real_client: TestClient) -> None:
    payload = real_client.get(f"/v1/runs/{REAL_RUN_ID}/reviews").json()
    assert len(payload["actionable"]) == 1
    assert payload["actionable"][0]["source"] == "identity"
    assert len(payload["audit"]) == 9
    assert len(payload["state_review"]) == 4
    assert all(item["source"] == "appearance_states" for item in payload["state_review"])
