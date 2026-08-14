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
    max_chunk_input_tokens: int = Field(default=10_000, gt=0)
    max_task_attempts: int = Field(default=3, ge=1)
    worker_lease_seconds: int = Field(default=120, ge=10)
    llm_provider: Literal["mock", "deepseek", "openai_compatible"] = "mock"
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str | None = None
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
        if self.app_env == "production" and self.llm_provider == "mock":
            raise ValueError("mock_llm_provider_forbidden_in_production")
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
