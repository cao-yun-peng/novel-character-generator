import pytest

from novel_character_generator.infrastructure.image.mock import MockImageProvider
from novel_character_generator.infrastructure.image.registry import (
    ImageProviderRegistry,
    create_image_provider,
)
from novel_character_generator.settings import Settings


class ExperimentalImageProvider(MockImageProvider):
    provider = "experimental"
    version = "market-model-v1"


class WrongIdentityProvider(MockImageProvider):
    provider = "wrong-name"


def test_registry_builds_custom_provider_without_orchestration_changes() -> None:
    registry = ImageProviderRegistry()
    registry.register("experimental", lambda _: ExperimentalImageProvider())
    settings = Settings(_env_file=None, image_provider="EXPERIMENTAL")

    provider = registry.create(settings.image_provider, settings)

    assert provider.provider == "experimental"
    assert provider.version == "market-model-v1"
    assert registry.names() == ("experimental",)


def test_registry_fails_closed_for_unknown_duplicate_and_identity_mismatch() -> None:
    registry = ImageProviderRegistry()
    registry.register("experimental", lambda _: ExperimentalImageProvider())
    settings = Settings(_env_file=None, image_provider="unknown")

    with pytest.raises(RuntimeError, match="provider_not_registered:unknown"):
        registry.create(settings.image_provider, settings)
    with pytest.raises(ValueError, match="already_registered"):
        registry.register("experimental", lambda _: ExperimentalImageProvider())
    with pytest.raises(ValueError, match="invalid_image_provider_name"):
        registry.register("disabled", lambda _: ExperimentalImageProvider())

    mismatch = ImageProviderRegistry()
    mismatch.register("experimental", lambda _: WrongIdentityProvider())
    with pytest.raises(RuntimeError, match="identity_mismatch"):
        mismatch.create("experimental", settings)


def test_settings_accept_provider_plugins_but_never_silently_falls_back() -> None:
    settings = Settings(_env_file=None, image_provider=" market-model ")
    assert settings.image_provider == "market-model"

    with pytest.raises(ValueError, match="invalid_image_provider_name"):
        Settings(_env_file=None, image_provider="   ")


@pytest.mark.asyncio
async def test_builtin_registry_builds_timicc_without_worker_changes(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        image_provider="timicc",
        timicc_api_key="test-key",
        timicc_image_staging_root=tmp_path,
    )

    provider = create_image_provider(settings)
    try:
        assert provider.provider == "timicc"
        assert provider.version == "gpt-image-2"
        assert provider.prompt_renderer_version == "canonical-zh-character-v1"
    finally:
        await provider.close()
