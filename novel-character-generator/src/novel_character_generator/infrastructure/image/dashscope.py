from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

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

_CREATE_PATH = "/api/v1/services/aigc/text2image/image-synthesis"
_ALLOWED_SIZES = {
    "1664*928",
    "1472*1104",
    "1328*1328",
    "1104*1472",
    "928*1664",
}
_ALLOWED_DASHSCOPE_HOSTS = {
    "dashscope.aliyuncs.com",
    "dashscope-intl.aliyuncs.com",
    "dashscope-us.aliyuncs.com",
}


class DashScopeImageProvider:
    provider = "dashscope"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "qwen-image-plus",
        default_size: str = "1328*1328",
        timeout_seconds: float = 30.0,
        prompt_renderer: ImagePromptRenderer | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if model not in {"qwen-image-plus", "qwen-image"}:
            raise ValueError("dashscope_async_image_model_unsupported")
        if default_size not in _ALLOWED_SIZES:
            raise ValueError("dashscope_image_size_unsupported")
        parsed_base_url = urlparse(base_url)
        base_hostname = (parsed_base_url.hostname or "").lower()
        if (
            parsed_base_url.scheme != "https"
            or (
                base_hostname not in _ALLOWED_DASHSCOPE_HOSTS
                and not base_hostname.endswith(".maas.aliyuncs.com")
            )
        ):
            raise ValueError("dashscope_base_url_not_allowed")
        normalized_path = parsed_base_url.path.rstrip("/")
        if normalized_path not in {"", "/api/v1"}:
            raise ValueError("dashscope_base_url_path_not_allowed")
        normalized_base_url = base_url.rstrip("/")
        if normalized_path == "/api/v1":
            normalized_base_url = normalized_base_url[: -len("/api/v1")]
        renderer = prompt_renderer or CanonicalChinesePromptRendererV1()
        self.version = model
        self.prompt_renderer = renderer.renderer
        self.prompt_renderer_version = renderer.version
        self._api_key = api_key
        self._model = model
        self._prompt_renderer = renderer
        self._default_size = default_size
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=normalized_base_url,
            timeout=timeout_seconds,
        )

    async def submit(self, request: ImageSubmitRequest) -> ImageSubmission:
        rendered_prompt = self._prompt_renderer.render(request.render_spec)
        prompt = rendered_prompt.positive_prompt
        negative_prompt = rendered_prompt.negative_prompt
        if len(prompt) > 800:
            raise ImageProviderSubmissionRejected("dashscope_prompt_exceeds_800_chars")
        if len(negative_prompt) > 500:
            raise ImageProviderSubmissionRejected(
                "dashscope_negative_prompt_exceeds_500_chars"
            )
        size = _resolve_size(request.render_spec, self._default_size)
        try:
            response = await self._client.post(
                _CREATE_PATH,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json={
                    "model": self._model,
                    "input": {"prompt": prompt},
                    "parameters": {
                        "negative_prompt": negative_prompt,
                        "size": size,
                        "n": 1,
                        "prompt_extend": False,
                        "watermark": False,
                        "seed": request.seed,
                    },
                },
            )
        except httpx.RequestError:
            # The remote side may have accepted the paid task; callers must
            # treat transport failures as submission-unknown and never blind-retry.
            raise
        if response.status_code >= 400:
            raise ImageProviderSubmissionRejected(_provider_error(response))
        payload = _json_object(response)
        output = payload.get("output")
        task_id = output.get("task_id") if isinstance(output, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError("dashscope_submit_response_missing_task_id")
        return ImageSubmission(provider_request_id=task_id, status="submitted")

    async def query(self, provider_request_id: str) -> ImageRemoteStatus:
        response = await self._client.get(
            f"/api/v1/tasks/{provider_request_id}",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        if response.status_code >= 400:
            return ImageRemoteStatus(status="failed", error_code=_provider_error(response))
        payload = _json_object(response)
        output = payload.get("output")
        if not isinstance(output, dict):
            return ImageRemoteStatus(
                status="failed", error_code="dashscope_query_response_missing_output"
            )
        status = str(output.get("task_status", "UNKNOWN")).upper()
        if status == "PENDING":
            return ImageRemoteStatus(status="submitted")
        if status == "RUNNING":
            return ImageRemoteStatus(status="running")
        if status != "SUCCEEDED":
            error_code = output.get("code") or payload.get("code") or status
            return ImageRemoteStatus(status="failed", error_code=str(error_code))
        results = output.get("results")
        artifact_refs: list[str] = []
        if isinstance(results, list):
            artifact_refs = [
                str(item["url"])
                for item in results
                if isinstance(item, dict) and isinstance(item.get("url"), str)
            ]
        if not artifact_refs:
            return ImageRemoteStatus(
                status="failed", error_code="dashscope_result_url_missing"
            )
        return ImageRemoteStatus(status="succeeded", artifact_refs=artifact_refs)

    async def download(self, artifact_ref: str) -> bytes:
        parsed = urlparse(artifact_ref)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname.endswith(".aliyuncs.com"):
            raise ValueError("dashscope_artifact_url_not_allowed")
        response = await self._client.get(artifact_ref)
        response.raise_for_status()
        return response.content

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


def compile_dashscope_prompt(spec: ImageRenderSpec) -> str:
    """Backward-compatible helper using the current default renderer."""
    return CanonicalChinesePromptRendererV1().render(spec).positive_prompt


def _resolve_size(spec: ImageRenderSpec, default_size: str) -> str:
    raw_size = spec.output_parameters.get("size")
    if raw_size is None:
        width = spec.output_parameters.get("width")
        height = spec.output_parameters.get("height")
        raw_size = f"{width}*{height}" if width is not None and height is not None else None
    size = str(raw_size or default_size)
    if size not in _ALLOWED_SIZES:
        raise ImageProviderSubmissionRejected("dashscope_image_size_unsupported")
    return size


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError("dashscope_response_not_json") from error
    if not isinstance(payload, dict):
        raise RuntimeError("dashscope_response_not_object")
    return payload


def _provider_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"dashscope_http_{response.status_code}"
    if not isinstance(payload, dict):
        return f"dashscope_http_{response.status_code}"
    code = str(payload.get("code") or f"HTTP_{response.status_code}")
    request_id = payload.get("request_id")
    return f"dashscope:{code}:request_id={request_id}" if request_id else f"dashscope:{code}"
