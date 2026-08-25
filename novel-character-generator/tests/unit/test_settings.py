import pytest
from pydantic import ValidationError

from novel_character_generator.settings import Settings


def test_default_settings_use_async_sqlite() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("sqlite+aiosqlite:///")
    assert settings.worker_lease_seconds >= 10
    assert settings.max_chunk_input_tokens == 5_000
    assert settings.chunk_overlap_tokens == 300
    assert settings.llm_timeout_seconds == 180
    assert settings.worker_lease_seconds > settings.llm_timeout_seconds


def test_chunk_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(
        ValidationError,
        match="chunk_overlap_must_be_smaller_than_chunk_size",
    ):
        Settings(_env_file=None, max_chunk_input_tokens=1_000, chunk_overlap_tokens=1_000)


def test_retrieval_overlap_and_embedding_configuration_are_validated() -> None:
    with pytest.raises(
        ValidationError,
        match="retrieval_overlap_must_be_smaller_than_passage_size",
    ):
        Settings(
            _env_file=None,
            retrieval_passage_target_tokens=100,
            retrieval_passage_overlap_tokens=100,
        )
    with pytest.raises(ValidationError, match="embedding_provider_configuration_required"):
        Settings(_env_file=None, embedding_provider="openai_compatible")

    settings = Settings(
        _env_file=None,
        embedding_provider="openai_compatible",
        embedding_base_url="https://embedding.test/v1",
        embedding_api_key="secret",
        embedding_model="embed-v1",
        embedding_dimension=3,
        embedding_profile_version="embed-profile-v1",
    )
    assert settings.embedding_dimension == 3
    assert settings.retrieval_rrf_k == 60


def test_llm_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_timeout_seconds=0)


def test_production_rejects_mock_provider() -> None:
    with pytest.raises(ValidationError, match="mock_llm_provider_forbidden_in_production"):
        Settings(_env_file=None, app_env="production")


def test_remote_provider_requires_credentials() -> None:
    with pytest.raises(ValidationError, match="llm_provider_credentials_required"):
        Settings(_env_file=None, llm_provider="deepseek")


def test_production_requires_distinct_user_and_admin_keys() -> None:
    provider = {
        "app_env": "production",
        "llm_provider": "deepseek",
        "llm_api_key": "llm-secret",
        "llm_model": "model-v1",
    }
    with pytest.raises(ValidationError, match="production_api_keys_required"):
        Settings(_env_file=None, **provider)
    with pytest.raises(ValidationError, match="production_api_keys_must_differ"):
        Settings(
            _env_file=None,
            **provider,
            user_api_key="same",
            admin_api_key="same",
        )
