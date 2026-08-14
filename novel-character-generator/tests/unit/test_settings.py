from novel_character_generator.settings import Settings


def test_default_settings_use_async_sqlite() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("sqlite+aiosqlite:///")
    assert settings.worker_lease_seconds >= 10
