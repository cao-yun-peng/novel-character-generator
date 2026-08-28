from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    otel_enabled: bool = True
    otel_service_name: str = "novel-character-generator-api"
    otel_exporter_otlp_endpoint: str | None = None
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    artifact_store: Literal["local"] = "local"
    artifact_local_root: Path = Path("data/artifacts")
    max_upload_bytes: int = Field(default=20_000_000, gt=0)
    max_chunk_input_tokens: int = Field(default=5_000, ge=1_000, le=12_000)
    chunk_overlap_tokens: int = Field(default=300, ge=0)
    retrieval_index_version: str = "retrieval-v1"
    retrieval_passage_target_tokens: int = Field(default=1_000, ge=32, le=12_000)
    retrieval_passage_overlap_tokens: int = Field(default=100, ge=0)
    retrieval_lexical_provider: Literal["sqlite_fts5"] = "sqlite_fts5"
    retrieval_lexical_profile_version: str = "zh-char-bigram-visual-v1"
    retrieval_vector_store: Literal["qdrant_local"] = "qdrant_local"
    qdrant_local_path: Path = Path("data/qdrant")
    embedding_provider: Literal["disabled", "openai_compatible"] = "disabled"
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None
    embedding_model_revision: str | None = None
    embedding_dimension: int | None = Field(default=None, gt=0)
    embedding_profile_version: str | None = None
    embedding_normalization: Literal["none", "l2"] = "l2"
    embedding_document_prefix: str = "passage: "
    embedding_query_prefix: str = "query: "
    embedding_batch_size: int = Field(default=16, ge=1, le=256)
    embedding_timeout_seconds: float = Field(default=60.0, gt=0)
    embedding_max_retries: int = Field(default=3, ge=0, le=10)
    retrieval_bm25_top_k: int = Field(default=40, ge=1, le=200)
    retrieval_vector_top_k: int = Field(default=40, ge=1, le=200)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=1_000)
    retrieval_main_hit_limit: int = Field(default=16, ge=1, le=100)
    retrieval_neighbor_count: int = Field(default=1, ge=1, le=3)
    visual_enrichment_max_provider_calls: int = Field(default=1, ge=1, le=8)
    visual_enrichment_context_budget_tokens: int = Field(default=8_000, ge=256, le=64_000)
    visual_enrichment_timeout_seconds: float = Field(default=180.0, gt=0)
    max_task_attempts: int = Field(default=3, ge=1)
    worker_lease_seconds: int = Field(default=240, ge=10)
    llm_provider: Literal["mock", "deepseek", "openai_compatible"] = "mock"
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=180.0, gt=0)
    llm_wire_api: Literal["chat_completions", "responses"] = "chat_completions"
    llm_thinking_enabled: bool = False
    llm_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    llm_max_output_tokens: int = Field(default=8_192, ge=256, le=65_536)
    llm_total_deadline_seconds: float = Field(default=120.0, gt=0)
    llm_max_items_per_result: int = Field(default=256, ge=1, le=2_000)
    llm_max_retries: int = Field(default=1, ge=0, le=3)
    llm_raw_response_capture_enabled: bool = False
    entity_resolution_context_budget_tokens: int = Field(
        default=12_000, ge=2_000, le=64_000
    )
    entity_resolution_memory_max_records: int = Field(default=64, ge=1, le=2_000)
    entity_resolution_memory_recent_records: int = Field(default=16, ge=0, le=2_000)
    # Provisional failure-informed limits: one observed 35-mention/21-record batch reached
    # 100% coverage, while 46 mentions/27 records collapsed to 32.6%. Recalibrate from
    # traced p95/p99 coverage and token usage after representative Provider reruns.
    entity_convergence_shard_max_records: int = Field(default=16, ge=1, le=2_000)
    entity_convergence_shard_max_mentions: int = Field(default=32, ge=1, le=2_000)
    entity_convergence_shard_max_input_tokens: int = Field(
        default=12_000, ge=1_000, le=128_000
    )
    entity_convergence_shard_max_output_tokens: int = Field(
        default=4_500, ge=256, le=65_536
    )
    entity_convergence_repair_max_attempts: int = Field(default=2, ge=0, le=4)
    entity_resolution_max_calls_per_run: int = Field(default=2_000, ge=1, le=100_000)
    image_provider: str = "disabled"
    image_prompt_renderer: str = "canonical-zh"
    image_workflow_profile: str = "mock-character-portrait"
    image_workflow_version: str = "1"
    image_candidate_count_max: int = Field(default=4, ge=1, le=8)
    dashscope_api_key: SecretStr | None = None
    dashscope_base_url: str | None = None
    dashscope_image_model: Literal["qwen-image-plus", "qwen-image"] = (
        "qwen-image-plus"
    )
    dashscope_image_default_size: Literal[
        "1664*928", "1472*1104", "1328*1328", "1104*1472", "928*1664"
    ] = "1328*1328"
    dashscope_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    timicc_api_key: SecretStr | None = None
    timicc_base_url: str = "https://timicc.com"
    timicc_image_model: Literal["gpt-image-2", "gpt-image-2-2026-04-21"] = (
        "gpt-image-2"
    )
    timicc_image_quality: Literal["low", "medium", "high", "auto"] = "medium"
    timicc_image_default_size: str = "1328x1328"
    timicc_image_staging_root: Path = Path("data/provider-staging/timicc")
    timicc_timeout_seconds: float = Field(default=180.0, gt=0, le=600)
    image_poll_interval_seconds: float = Field(default=10.0, ge=1, le=60)
    agent_runtime_enabled: bool = False
    agent_max_turns_default: int = Field(default=3, ge=1)
    agent_max_tool_calls_default: int = Field(default=12, ge=0)
    agent_max_reflection_rounds: int = Field(default=1, ge=0)
    agent_max_cost_default: Decimal = Field(default=Decimal("1.0"), gt=0)
    agent_deadline_seconds_default: int = Field(default=180, ge=1)
    agent_tool_write_policy: Literal["approval_required"] = "approval_required"
    auth_mode: Literal["api_key"] = "api_key"
    user_api_key: SecretStr | None = None
    admin_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def validate_provider_configuration(self) -> "Settings":
        self.image_provider = self.image_provider.strip().lower()
        self.image_prompt_renderer = self.image_prompt_renderer.strip().lower()
        if not self.image_provider:
            raise ValueError("invalid_image_provider_name")
        if not self.image_prompt_renderer:
            raise ValueError("invalid_image_prompt_renderer_name")
        for field_name in (
            "llm_api_key",
            "embedding_api_key",
            "dashscope_api_key",
            "timicc_api_key",
            "user_api_key",
            "admin_api_key",
        ):
            secret = getattr(self, field_name)
            if secret is not None and not secret.get_secret_value():
                setattr(self, field_name, None)
        if self.chunk_overlap_tokens >= self.max_chunk_input_tokens:
            raise ValueError("chunk_overlap_must_be_smaller_than_chunk_size")
        if self.retrieval_passage_overlap_tokens >= self.retrieval_passage_target_tokens:
            raise ValueError("retrieval_overlap_must_be_smaller_than_passage_size")
        if self.embedding_provider != "disabled" and (
            self.embedding_api_key is None
            or not self.embedding_base_url
            or not self.embedding_model
            or self.embedding_dimension is None
            or not self.embedding_profile_version
        ):
            raise ValueError("embedding_provider_configuration_required")
        if self.llm_total_deadline_seconds >= self.worker_lease_seconds:
            raise ValueError("llm_deadline_must_be_shorter_than_worker_lease")
        if (
            self.entity_resolution_memory_recent_records
            > self.entity_resolution_memory_max_records
        ):
            raise ValueError("entity_resolution_memory_recent_exceeds_max_records")
        if self.entity_convergence_shard_max_output_tokens > self.llm_max_output_tokens:
            raise ValueError("entity_convergence_output_budget_exceeds_provider_limit")
        if self.app_env == "production" and self.llm_provider == "mock":
            raise ValueError("mock_llm_provider_forbidden_in_production")
        if self.app_env == "production" and self.image_provider == "mock":
            raise ValueError("mock_image_provider_forbidden_in_production")
        if self.image_provider == "dashscope" and (
            self.dashscope_api_key is None or not self.dashscope_base_url
        ):
            raise ValueError("dashscope_image_provider_configuration_required")
        if self.image_provider == "timicc" and (
            self.timicc_api_key is None or not self.timicc_base_url
        ):
            raise ValueError("timicc_image_provider_configuration_required")
        if self.app_env == "production" and self.llm_raw_response_capture_enabled:
            raise ValueError("llm_raw_response_capture_forbidden_in_production")
        if self.llm_provider != "mock" and (self.llm_api_key is None or not self.llm_model):
            raise ValueError("llm_provider_credentials_required")
        if self.app_env == "production":
            if self.user_api_key is None or self.admin_api_key is None:
                raise ValueError("production_api_keys_required")
            if self.user_api_key.get_secret_value() == self.admin_api_key.get_secret_value():
                raise ValueError("production_api_keys_must_differ")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
