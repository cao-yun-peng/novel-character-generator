from fastapi.testclient import TestClient

from novel_character_generator.api.app import create_app


def test_health_endpoints() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"status": "ok"}
