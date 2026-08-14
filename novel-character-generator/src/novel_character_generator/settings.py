from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
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
    max_chunk_input_tokens: int = Field(default=10_000, gt=0)
    max_task_attempts: int = Field(default=3, ge=1)
    worker_lease_seconds: int = Field(default=120, ge=10)
    agent_runtime_enabled: bool = False
    auth_mode: Literal["api_key"] = "api_key"
    admin_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
