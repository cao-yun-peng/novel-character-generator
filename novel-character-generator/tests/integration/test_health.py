from fastapi.testclient import TestClient

from novel_character_generator.api.app import create_app
from novel_character_generator.settings import get_settings


def test_health_endpoints() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"status": "ok"}


def test_ui_shell_and_static_assets_are_served_without_api_auth() -> None:
    with TestClient(create_app()) as client:
        root = client.get("/", follow_redirects=False)
        assert root.status_code == 302
        assert root.headers["location"] == "/ui"

        page = client.get("/ui")
        assert page.status_code == 200
        assert "角色造像台" in page.text
        assert 'id="approvals"' in page.text
        assert 'id="reviewer-id"' in page.text
        assert 'id="approval-list"' in page.text
        assert 'id="conflict-review-list"' in page.text
        assert 'id="render-profile-review"' in page.text
        assert 'id="restart-run-button"' in page.text
        assert 'id="cancel-run-button"' in page.text
        assert "/ui/assets/app.css" in page.text
        assert "/ui/assets/app.js" in page.text

        css = client.get("/ui/assets/app.css")
        javascript = client.get("/ui/assets/app.js")
        favicon = client.get("/ui/assets/favicon.svg")
        assert css.status_code == 200
        assert css.headers["content-type"].startswith("text/css")
        assert javascript.status_code == 200
        assert "loadCapabilities" in javascript.text
        assert "loadApprovals" in javascript.text
        assert "resolveCharacterConflict" in javascript.text
        assert "saveRenderProfile" in javascript.text
        assert "approveRenderProfile" in javascript.text
        assert "loadPartialAnalysis" in javascript.text
        assert "current_chunk_ordinal" in javascript.text
        assert "restartAnalysis" in javascript.text
        assert "cancelRun" in javascript.text
        assert "renderFactSection" in javascript.text
        assert "loadVisualEnrichmentState" in javascript.text
        assert "startVisualEnrichment" in javascript.text
        assert "resolveFeatureSuggestion" in javascript.text
        assert "visual-field-gaps" in javascript.text
        assert "ensureRetrievalIndex" in javascript.text
        assert "retrieval-index-runs" in javascript.text
        assert "life_phase_label" in javascript.text
        assert favicon.status_code == 200
        assert favicon.headers["content-type"].startswith("image/svg+xml")

    assert "/ui" not in create_app().openapi()["paths"]


def test_validation_errors_use_stable_envelope() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/runs/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["message"] == "Request validation failed"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_openapi_exposes_documented_phase_one_routes() -> None:
    schema = create_app().openapi()
    paths = set(schema["paths"])
    assert {
        "/api/v1/novels",
        "/api/v1/novels/{novel_id}",
        "/api/v1/novels/{novel_id}/runs",
        "/api/v1/novels/{novel_id}/retrieval-index-runs",
        "/api/v1/runs/{run_id}",
        "/api/v1/runs/{run_id}/events",
        "/api/v1/runs/{run_id}/agent-runs",
        "/api/v1/runs/{run_id}/external-operations",
        "/api/v1/agent-runs/{agent_run_id}",
        "/api/v1/approvals",
        "/api/v1/approvals/{approval_id}/resolve",
        "/api/v1/novels/{novel_id}/characters",
        "/api/v1/novels/{novel_id}/timelines",
        "/api/v1/novels/{novel_id}/events",
        "/api/v1/novels/{novel_id}/scenes",
        "/api/v1/scenes/{scene_id}/temporal-binding",
        "/api/v1/characters/merge",
        "/api/v1/characters/{character_id}/split",
        "/api/v1/characters/{character_id}/visual-enrichment-runs",
        "/api/v1/characters/{character_id}/visual-field-gaps",
        "/api/v1/visual-enrichment-runs/{run_id}/evidence",
        "/api/v1/feature-suggestions/{suggestion_id}/resolve",
        "/api/v1/capabilities",
    } <= paths
    assert "/api/v1/novels/{novel_id}/extraction-runs" not in paths


def test_api_key_roles_capabilities_and_metrics(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("USER_API_KEY", "user-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/api/v1/capabilities").status_code == 401
            capabilities = client.get(
                "/api/v1/capabilities", headers={"X-API-Key": "user-secret"}
            )
            assert capabilities.status_code == 200
            assert capabilities.json()["document_versioning"] is True
            assert capabilities.json()["story_temporal_binding"] is True
            assert capabilities.json()["character_entity_resolution"] is True
            assert capabilities.json()["appearance_aggregation"] is True
            assert capabilities.json()["retrieval_lexical_index"] is True
            assert capabilities.json()["retrieval_hybrid_index"] is False
            assert capabilities.json()["external_operation_reconciliation"] is False
            assert client.get("/metrics", headers={"X-API-Key": "user-secret"}).status_code == 403
            metrics = client.get("/metrics", headers={"X-API-Key": "admin-secret"})
            assert metrics.status_code == 200
            assert "novel_character_generator_http_requests_total" in metrics.text
            assert 'route="/api/v1/capabilities"' in metrics.text
    finally:
        get_settings.cache_clear()
