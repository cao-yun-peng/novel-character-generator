from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NCG_", extra="ignore")

    app_name: str = "Novel Character Generator"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    artifact_root: Path = Path("data/artifacts")
    worker_lease_seconds: int = 120
    worker_poll_seconds: float = 0.2
    max_task_attempts: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
