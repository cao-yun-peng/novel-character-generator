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
    assert settings.llm_wire_api == "chat_completions"
    assert settings.llm_thinking_enabled is False
    assert settings.llm_reasoning_effort == "none"
    assert settings.llm_max_output_tokens == 8_192
    assert settings.llm_total_deadline_seconds == 120
    assert settings.llm_max_items_per_result == 256
    assert settings.llm_max_retries == 1
    assert settings.llm_raw_response_capture_enabled is False
    assert settings.entity_resolution_memory_max_records == 64
    assert settings.entity_resolution_memory_recent_records == 16
    assert settings.entity_convergence_shard_max_records == 16
    assert settings.entity_convergence_shard_max_mentions == 32
    assert settings.entity_convergence_shard_max_input_tokens == 12_000
    assert settings.entity_convergence_shard_max_output_tokens == 4_500
    assert settings.entity_convergence_repair_max_attempts == 2
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


def test_llm_deadline_must_fit_inside_worker_lease() -> None:
    with pytest.raises(ValidationError, match="llm_deadline_must_be_shorter_than_worker_lease"):
        Settings(
            _env_file=None,
            llm_total_deadline_seconds=240,
            worker_lease_seconds=240,
        )


def test_entity_resolution_recent_memory_must_fit_inside_record_limit() -> None:
    with pytest.raises(
        ValidationError,
        match="entity_resolution_memory_recent_exceeds_max_records",
    ):
        Settings(
            _env_file=None,
            entity_resolution_memory_max_records=4,
            entity_resolution_memory_recent_records=5,
        )


def test_entity_convergence_output_budget_must_fit_provider_limit() -> None:
    with pytest.raises(
        ValidationError,
        match="entity_convergence_output_budget_exceeds_provider_limit",
    ):
        Settings(
            _env_file=None,
            llm_max_output_tokens=1_000,
            entity_convergence_shard_max_output_tokens=1_001,
        )


def test_production_rejects_mock_provider() -> None:
    with pytest.raises(ValidationError, match="mock_llm_provider_forbidden_in_production"):
        Settings(_env_file=None, app_env="production")
    with pytest.raises(ValidationError, match="mock_image_provider_forbidden_in_production"):
        Settings(
            _env_file=None,
            app_env="production",
            llm_provider="deepseek",
            llm_api_key="secret",
            llm_model="model-v1",
            image_provider="mock",
        )


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


def test_production_rejects_raw_model_response_capture() -> None:
    with pytest.raises(
        ValidationError,
        match="llm_raw_response_capture_forbidden_in_production",
    ):
        Settings(
            _env_file=None,
            app_env="production",
            llm_provider="deepseek",
            llm_api_key="llm-secret",
            llm_model="model-v1",
            user_api_key="user-secret",
            admin_api_key="admin-secret",
            llm_raw_response_capture_enabled=True,
        )
