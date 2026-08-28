from __future__ import annotations

from collections.abc import Callable

from novel_character_generator.application.ports.image_generation import ImageProvider
from novel_character_generator.infrastructure.image.dashscope import DashScopeImageProvider
from novel_character_generator.infrastructure.image.mock import MockImageProvider
from novel_character_generator.infrastructure.image.openai_compatible import (
    OpenAICompatibleImageProvider,
)
from novel_character_generator.infrastructure.image.prompting import (
    create_image_prompt_renderer,
)
from novel_character_generator.settings import Settings

ImageProviderFactory = Callable[[Settings], ImageProvider]


class ImageProviderRegistry:
    """Composition-root registry; orchestration remains vendor-neutral."""

    def __init__(self) -> None:
        self._factories: dict[str, ImageProviderFactory] = {}

    def register(self, name: str, factory: ImageProviderFactory) -> None:
        normalized = name.strip().lower()
        if not normalized or normalized == "disabled":
            raise ValueError("invalid_image_provider_name")
        if normalized in self._factories:
            raise ValueError(f"image_provider_already_registered:{normalized}")
        self._factories[normalized] = factory

    def create(self, name: str, settings: Settings) -> ImageProvider:
        normalized = name.strip().lower()
        if normalized == "disabled":
            raise RuntimeError("image_generation_provider_disabled")
        factory = self._factories.get(normalized)
        if factory is None:
            available = ",".join(self.names())
            raise RuntimeError(
                f"image_generation_provider_not_registered:{normalized};available={available}"
            )
        provider = factory(settings)
        if provider.provider != normalized:
            raise RuntimeError(
                f"image_provider_identity_mismatch:{normalized}:{provider.provider}"
            )
        return provider

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def _create_mock(_: Settings) -> ImageProvider:
    return MockImageProvider()


def _create_dashscope(settings: Settings) -> ImageProvider:
    if settings.dashscope_api_key is None or settings.dashscope_base_url is None:
        raise RuntimeError("dashscope_image_provider_configuration_required")
    return DashScopeImageProvider(
        api_key=settings.dashscope_api_key.get_secret_value(),
        base_url=settings.dashscope_base_url,
        model=settings.dashscope_image_model,
        default_size=settings.dashscope_image_default_size,
        timeout_seconds=settings.dashscope_timeout_seconds,
        prompt_renderer=create_image_prompt_renderer(settings.image_prompt_renderer),
    )


def _create_timicc(settings: Settings) -> ImageProvider:
    if settings.timicc_api_key is None:
        raise RuntimeError("timicc_image_provider_configuration_required")
    return OpenAICompatibleImageProvider(
        provider="timicc",
        api_key=settings.timicc_api_key.get_secret_value(),
        base_url=settings.timicc_base_url,
        model=settings.timicc_image_model,
        allowed_hosts={"timicc.com"},
        staging_root=settings.timicc_image_staging_root,
        quality=settings.timicc_image_quality,
        default_size=settings.timicc_image_default_size,
        timeout_seconds=settings.timicc_timeout_seconds,
        prompt_renderer=create_image_prompt_renderer(settings.image_prompt_renderer),
    )


image_provider_registry = ImageProviderRegistry()
image_provider_registry.register("mock", _create_mock)
image_provider_registry.register("dashscope", _create_dashscope)
image_provider_registry.register("timicc", _create_timicc)


def create_image_provider(settings: Settings) -> ImageProvider:
    return image_provider_registry.create(settings.image_provider, settings)
