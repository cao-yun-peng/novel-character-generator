from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from novel_character_generator.application.ports.image_generation import (
    ImagePromptRenderer,
    ImageProviderCapabilities,
    ImageProviderSubmissionRejected,
    ImageRemoteStatus,
    ImageSubmission,
    ImageSubmitRequest,
)
from novel_character_generator.domain.entities.image import ImageRenderSpec
from novel_character_generator.infrastructure.image.prompting import (
    CanonicalChinesePromptRendererV1,
)

_CREATE_PATH = "/v1/images/generations"
_PNG_HEADER = b"\x89PNG\r\n\x1a\n"
_MAX_IMAGE_BYTES = 20_000_000
_PROVIDER_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_STAGED_REF_PATH = re.compile(r"^/([0-9a-f]{64})\.png$")
_SIZE = re.compile(r"^(\d+)\s*([x*])\s*(\d+)$")


class OpenAICompatibleImageProvider:
    """Synchronous OpenAI Images adapter with restart-safe local staging."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        base_url: str,
        model: str,
        allowed_hosts: set[str],
        staging_root: Path,
        quality: str = "medium",
        default_size: str = "1024x1024",
        timeout_seconds: float = 180.0,
        prompt_renderer: ImagePromptRenderer | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized_provider = provider.strip().lower()
        if not _PROVIDER_NAME.fullmatch(normalized_provider):
            raise ValueError("openai_compatible_image_provider_name_invalid")
        if not api_key:
            raise ValueError("openai_compatible_image_api_key_required")
        if not model.strip():
            raise ValueError("openai_compatible_image_model_required")
        if quality not in {"low", "medium", "high", "auto"}:
            raise ValueError("openai_compatible_image_quality_unsupported")

        normalized_base_url = _validate_base_url(base_url, allowed_hosts)
        renderer = prompt_renderer or CanonicalChinesePromptRendererV1()
        self.provider = normalized_provider
        self.version = model.strip()
        self.prompt_renderer = renderer.renderer
        self.prompt_renderer_version = renderer.version
        self._api_key = api_key
        self._model = model.strip()
        self._quality = quality
        self._default_size = _normalize_size(default_size)
        self._prompt_renderer = renderer
        self._staging_root = staging_root.resolve()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=normalized_base_url,
            timeout=timeout_seconds,
        )

    async def submit(self, request: ImageSubmitRequest) -> ImageSubmission:
        rendered = self._prompt_renderer.render(request.render_spec)
        prompt = rendered.positive_prompt
        if rendered.negative_prompt:
            prompt = f"{prompt}\n画面不得出现：{rendered.negative_prompt}。"
        if len(prompt) > 32_000:
            raise ImageProviderSubmissionRejected(
                "openai_compatible_image_prompt_exceeds_32000_chars"
            )
        size = _resolve_size(request.render_spec, self._default_size)
        try:
            response = await self._client.post(
                _CREATE_PATH,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "n": 1,
                    "size": size,
                    "quality": self._quality,
                    "output_format": "png",
                    "background": "opaque",
                },
            )
        except httpx.RequestError:
            # A synchronous paid request may have reached the relay. Preserve the
            # transport error so orchestration marks submission_unknown and does
            # not blindly charge for a retry.
            raise
        if response.status_code >= 400:
            raise ImageProviderSubmissionRejected(
                _provider_error(self.provider, response)
            )
        image = _decode_image_response(response)
        artifact_ref, digest = await asyncio.to_thread(self._stage_image, image)
        return ImageSubmission(
            provider_request_id=f"image-{digest[:24]}",
            status="succeeded",
            artifact_refs=[artifact_ref],
        )

    async def query(self, provider_request_id: str) -> ImageRemoteStatus:
        del provider_request_id
        return ImageRemoteStatus(
            status="failed",
            error_code="openai_compatible_synchronous_query_not_supported",
        )

    async def download(self, artifact_ref: str) -> bytes:
        parsed = urlparse(artifact_ref)
        match = _STAGED_REF_PATH.fullmatch(parsed.path)
        if (
            parsed.scheme != "staged-image"
            or parsed.netloc != self.provider
            or parsed.params
            or parsed.query
            or parsed.fragment
            or match is None
        ):
            raise ValueError("openai_compatible_artifact_ref_invalid")
        digest = match.group(1)
        target = self._staging_root / digest[:2] / f"{digest}.png"
        try:
            data = await asyncio.to_thread(target.read_bytes)
        except FileNotFoundError as error:
            raise ValueError("openai_compatible_artifact_missing") from error
        if hashlib.sha256(data).hexdigest() != digest or not data.startswith(_PNG_HEADER):
            raise ValueError("openai_compatible_artifact_integrity_failed")
        return data

    def capabilities(self) -> ImageProviderCapabilities:
        return ImageProviderCapabilities(
            idempotency=False,
            cancellation=False,
            request_fingerprint_lookup=False,
            cost_reporting=False,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _stage_image(self, image: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(image).hexdigest()
        directory = self._staging_root / digest[:2]
        target = directory / f"{digest}.png"
        directory.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = directory / f".{digest}.{uuid4().hex}.tmp"
            try:
                temporary.write_bytes(image)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return f"staged-image://{self.provider}/{digest}.png", digest


def _validate_base_url(base_url: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()
    normalized_allowed_hosts = {item.lower() for item in allowed_hosts}
    if (
        parsed.scheme != "https"
        or hostname not in normalized_allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("openai_compatible_image_base_url_not_allowed")
    normalized_path = parsed.path.rstrip("/")
    if normalized_path not in {"", "/v1"}:
        raise ValueError("openai_compatible_image_base_url_path_not_allowed")
    root = base_url.rstrip("/")
    if normalized_path == "/v1":
        root = root[: -len("/v1")]
    return root


def _resolve_size(spec: ImageRenderSpec, default_size: str) -> str:
    raw_size = spec.output_parameters.get("size")
    if raw_size is None:
        width = spec.output_parameters.get("width")
        height = spec.output_parameters.get("height")
        raw_size = f"{width}x{height}" if width is not None and height is not None else None
    return _normalize_size(str(raw_size or default_size))


def _normalize_size(raw_size: str) -> str:
    match = _SIZE.fullmatch(raw_size.strip())
    if match is None:
        raise ImageProviderSubmissionRejected(
            "openai_compatible_image_size_unsupported"
        )
    width, height = int(match.group(1)), int(match.group(3))
    if (
        width <= 0
        or height <= 0
        or width % 16
        or height % 16
        or max(width / height, height / width) > 3
        or max(width, height) > 3_840
        or width * height > 3_840 * 2_160
    ):
        raise ImageProviderSubmissionRejected(
            "openai_compatible_image_size_unsupported"
        )
    return f"{width}x{height}"


def _decode_image_response(response: httpx.Response) -> bytes:
    payload = _json_object(response)
    data = payload.get("data")
    first = data[0] if isinstance(data, list) and data else None
    encoded = first.get("b64_json") if isinstance(first, dict) else None
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError("openai_compatible_image_response_missing_b64_json")
    try:
        image = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise RuntimeError("openai_compatible_image_response_invalid_base64") from error
    if len(image) > _MAX_IMAGE_BYTES:
        raise ValueError("openai_compatible_image_artifact_too_large")
    if not image.startswith(_PNG_HEADER):
        raise ValueError("openai_compatible_image_artifact_invalid_png")
    return image


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError("openai_compatible_image_response_not_json") from error
    if not isinstance(payload, dict):
        raise RuntimeError("openai_compatible_image_response_not_object")
    return payload


def _provider_error(provider: str, response: httpx.Response) -> str:
    code = f"HTTP_{response.status_code}"
    request_id = response.headers.get("x-request-id")
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or error.get("type") or code)
        else:
            code = str(payload.get("code") or code)
        payload_request_id = payload.get("request_id")
        if isinstance(payload_request_id, str):
            request_id = payload_request_id
    safe_code = re.sub(r"[^A-Za-z0-9_.-]", "_", code)[:80]
    safe_request_id = (
        re.sub(r"[^A-Za-z0-9_.-]", "_", request_id)[:80]
        if request_id
        else None
    )
    suffix = f":request_id={safe_request_id}" if safe_request_id else ""
    return f"{provider}:{safe_code}{suffix}"
