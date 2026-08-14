import pytest
from pydantic import ValidationError

from novel_character_generator.settings import Settings


def test_default_settings_use_async_sqlite() -> None:
    settings = Settings()
    assert settings.database_url.startswith("sqlite+aiosqlite:///")
    assert settings.worker_lease_seconds >= 10


def test_production_rejects_mock_provider() -> None:
    with pytest.raises(ValidationError, match="mock_llm_provider_forbidden_in_production"):
        Settings(app_env="production")


def test_remote_provider_requires_credentials() -> None:
    with pytest.raises(ValidationError, match="llm_provider_credentials_required"):
        Settings(llm_provider="deepseek")


def test_production_requires_distinct_user_and_admin_keys() -> None:
    provider = {
        "app_env": "production",
        "llm_provider": "deepseek",
        "llm_api_key": "llm-secret",
        "llm_model": "model-v1",
    }
    with pytest.raises(ValidationError, match="production_api_keys_required"):
        Settings(**provider)
    with pytest.raises(ValidationError, match="production_api_keys_must_differ"):
        Settings(**provider, user_api_key="same", admin_api_key="same")
