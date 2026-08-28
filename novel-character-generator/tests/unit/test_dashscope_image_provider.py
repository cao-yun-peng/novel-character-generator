import json

import httpx
import pytest

from novel_character_generator.application.ports.image_generation import (
    ImageProviderSubmissionRejected,
    ImageSubmitRequest,
)
from novel_character_generator.domain.entities.image import ImageRenderSpec
from novel_character_generator.infrastructure.image.dashscope import (
    DashScopeImageProvider,
    compile_dashscope_prompt,
)


def _spec(**overrides: object) -> ImageRenderSpec:
    source_ref = {"source_kind": "human_decision"}
    values: dict[str, object] = {
        "schema_version": "v1",
        "generation_mode": "concept",
        "identity_prompt_block": ["hair.color: black", "skin.color: 麦色"],
        "stage_prompt_block": ["age: 五至六岁", "body.build: 瘦小"],
        "outfit_prompt_block": ["clothing.style: 朴素整洁的旧布衣"],
        "performance_prompt_block": ["action: 安静坐着", "gaze: 望向东方"],
        "environment_prompt_block": [
            "environment.location: 山顶",
            "environment.time: 黎明",
            "environment.background: 远处薄雾",
        ],
        "art_direction_prompt_block": [
            "art_direction.medium: 东方玄幻插画",
            "composition.shot: full body",
            "art_direction.lighting: 柔和晨光",
        ],
        "negative_constraints": ["文字", "水印", "多余手指"],
        "output_parameters": {"size": "1328*1328"},
        "source_map": {
            path: [source_ref]
            for path in (
                "hair.color",
                "skin.color",
                "age",
                "body.build",
                "clothing.style",
                "action",
                "gaze",
                "environment.location",
                "environment.time",
                "environment.background",
                "art_direction.medium",
                "composition.shot",
                "art_direction.lighting",
                "negative_constraints[0]",
                "negative_constraints[1]",
                "negative_constraints[2]",
            )
        },
        "compiler_version": "image-render-spec-v1",
        "spec_hash": "a" * 64,
    }
    values.update(overrides)
    return ImageRenderSpec.model_validate(values)


def _request(spec: ImageRenderSpec | None = None) -> ImageSubmitRequest:
    return ImageSubmitRequest(
        context_hash="b" * 64,
        workflow_profile="qwen-character-portrait",
        workflow_version="1",
        candidate_index=0,
        seed=17,
        render_spec=spec or _spec(),
    )


@pytest.mark.asyncio
async def test_submit_uses_async_api_and_preserves_render_spec_boundaries() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "output": {"task_status": "PENDING", "task_id": "task-123"},
                "request_id": "request-123",
            },
        )

    client = httpx.AsyncClient(
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
        transport=httpx.MockTransport(handler),
    )
    provider = DashScopeImageProvider(
        api_key="secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
        client=client,
    )
    try:
        submission = await provider.submit(_request())
    finally:
        await client.aclose()

    assert submission.provider_request_id == "task-123"
    assert submission.status == "submitted"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["authorization"] == "Bearer secret"
    assert headers["x-dashscope-async"] == "enable"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen-image-plus"
    assert body["parameters"] == {
        "negative_prompt": "文字，水印，多余手指",
        "size": "1328*1328",
        "n": 1,
        "prompt_extend": False,
        "watermark": False,
        "seed": 17,
    }
    assert "角色身份：头发颜色为黑色；肤色为麦色。" in body["input"]["prompt"]
    assert "hair.color" not in body["input"]["prompt"]


@pytest.mark.asyncio
async def test_query_maps_pending_success_and_failed_statuses() -> None:
    responses = iter(
        [
            {"output": {"task_status": "RUNNING", "task_id": "task-123"}},
            {
                "output": {
                    "task_status": "SUCCEEDED",
                    "task_id": "task-123",
                    "results": [
                        {"url": "https://dashscope-result.oss-cn-beijing.aliyuncs.com/a.png"}
                    ],
                }
            },
            {"output": {"task_status": "FAILED", "code": "DataInspectionFailed"}},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, json=next(responses))

    client = httpx.AsyncClient(
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
        transport=httpx.MockTransport(handler),
    )
    provider = DashScopeImageProvider(
        api_key="secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
        client=client,
    )
    try:
        assert (await provider.query("task-123")).status == "running"
        succeeded = await provider.query("task-123")
        failed = await provider.query("task-123")
    finally:
        await client.aclose()

    assert succeeded.status == "succeeded"
    assert succeeded.artifact_refs[0].endswith("/a.png")
    assert failed.status == "failed"
    assert failed.error_code == "DataInspectionFailed"


@pytest.mark.asyncio
async def test_download_allows_only_https_aliyun_result_urls_without_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"\x89PNG\r\n\x1a\nimage")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DashScopeImageProvider(
        api_key="secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
        client=client,
    )
    try:
        data = await provider.download(
            "https://dashscope-result.oss-cn-beijing.aliyuncs.com/a.png?Expires=1"
        )
        with pytest.raises(ValueError, match="artifact_url_not_allowed"):
            await provider.download("https://attacker.example/a.png")
    finally:
        await client.aclose()
    assert data.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_definitive_rejection_is_distinct_from_submission_unknown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"code": "InvalidParameter", "request_id": "request-400"},
        )

    client = httpx.AsyncClient(
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
        transport=httpx.MockTransport(handler),
    )
    provider = DashScopeImageProvider(
        api_key="secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
        client=client,
    )
    try:
        with pytest.raises(ImageProviderSubmissionRejected, match="InvalidParameter"):
            await provider.submit(_request())
    finally:
        await client.aclose()


def test_prompt_and_size_limits_fail_closed() -> None:
    prompt = compile_dashscope_prompt(_spec())
    assert "不添加人物事实" in prompt

    with pytest.raises(ValueError, match="image_size_unsupported"):
        DashScopeImageProvider(
            api_key="secret",
            base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
            default_size="1024*1024",
        )


@pytest.mark.asyncio
async def test_official_shared_and_workspace_base_urls_are_allowed() -> None:
    shared = DashScopeImageProvider(
        api_key="secret",
        base_url="https://dashscope.aliyuncs.com/api/v1",
    )
    workspace = DashScopeImageProvider(
        api_key="secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com/api/v1",
    )

    assert shared.version == "qwen-image-plus"
    assert str(shared._client.base_url) == "https://dashscope.aliyuncs.com"
    assert workspace.prompt_renderer_version == "canonical-zh-character-v1"
    await shared.close()
    await workspace.close()

    with pytest.raises(ValueError, match="base_url_not_allowed"):
        DashScopeImageProvider(
            api_key="secret",
            base_url="https://attacker.example/api/v1",
        )
