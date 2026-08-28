import base64
from pathlib import Path

import httpx
import pytest

from novel_character_generator.application.ports.image_generation import (
    ImageProviderSubmissionRejected,
    ImageSubmitRequest,
)
from novel_character_generator.domain.entities.image import ImageRenderSpec
from novel_character_generator.infrastructure.image.openai_compatible import (
    OpenAICompatibleImageProvider,
)

PNG = b"\x89PNG\r\n\x1a\ncontract-test"


def _spec(*, size: str = "1328*1328") -> ImageRenderSpec:
    paths = [
        "hair.color",
        "age",
        "clothing.style",
        "pose.body",
        "environment.location",
        "art_direction.medium",
        "negative_constraints[0]",
    ]
    return ImageRenderSpec(
        schema_version="image-render-spec-v1",
        generation_mode="character_design",
        identity_prompt_block=["hair.color: black"],
        stage_prompt_block=["age: 五、六岁"],
        outfit_prompt_block=["clothing.style: 朴素灰色旧布衣"],
        performance_prompt_block=["pose.body: 安静坐在山石上"],
        environment_prompt_block=["environment.location: 山顶"],
        art_direction_prompt_block=[
            "art_direction.medium: 东方玄幻小说角色概念插画"
        ],
        negative_constraints=["文字"],
        output_parameters={"size": size},
        source_map={
            path: [{"source_kind": "human_decision"}] for path in paths
        },
        compiler_version="image-render-compiler-v1",
        spec_hash="a" * 64,
    )


def _request(*, size: str = "1328*1328") -> ImageSubmitRequest:
    return ImageSubmitRequest(
        context_hash="b" * 64,
        workflow_profile="gpt-image-character-baseline-candidate",
        workflow_version="1",
        candidate_index=0,
        seed=270827,
        render_spec=_spec(size=size),
    )


@pytest.mark.asyncio
async def test_submit_uses_gpt_image_contract_and_restart_safe_staging(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]},
        )

    client = httpx.AsyncClient(
        base_url="https://timicc.com",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAICompatibleImageProvider(
        provider="timicc",
        api_key="test-key",
        base_url="https://timicc.com/v1",
        model="gpt-image-2",
        allowed_hosts={"timicc.com"},
        staging_root=tmp_path,
        client=client,
    )
    try:
        submission = await provider.submit(_request())
        assert submission.status == "succeeded"
        assert submission.artifact_refs[0].startswith("staged-image://timicc/")
        assert await provider.download(submission.artifact_refs[0]) == PNG
        assert captured["path"] == "/v1/images/generations"
        assert captured["authorization"] == "Bearer test-key"
        body = str(captured["body"])
        assert '"model":"gpt-image-2"' in body
        assert '"size":"1328x1328"' in body
        assert '"quality":"medium"' in body
        assert '"output_format":"png"' in body
        assert '"seed"' not in body
        assert "hair.color" not in body
        assert "画面不得出现" in body
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_rejection_is_sanitized_and_distinct_from_transport_unknown(
    tmp_path: Path,
) -> None:
    def rejected(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-request-id": "request/unsafe"},
            json={
                "error": {
                    "code": "model_not_found",
                    "message": "echo test-key and the full prompt",
                }
            },
        )

    client = httpx.AsyncClient(
        base_url="https://timicc.com",
        transport=httpx.MockTransport(rejected),
    )
    provider = OpenAICompatibleImageProvider(
        provider="timicc",
        api_key="test-key",
        base_url="https://timicc.com",
        model="gpt-image-2",
        allowed_hosts={"timicc.com"},
        staging_root=tmp_path,
        client=client,
    )
    try:
        with pytest.raises(ImageProviderSubmissionRejected) as captured:
            await provider.submit(_request())
        error = str(captured.value)
        assert error == "timicc:model_not_found:request_id=request_unsafe"
        assert "test-key" not in error
        assert "full prompt" not in error
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_invalid_response_and_artifact_reference_fail_closed(
    tmp_path: Path,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"b64_json": "not base64"}]})

    client = httpx.AsyncClient(
        base_url="https://timicc.com",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAICompatibleImageProvider(
        provider="timicc",
        api_key="test-key",
        base_url="https://timicc.com",
        model="gpt-image-2",
        allowed_hosts={"timicc.com"},
        staging_root=tmp_path,
        client=client,
    )
    try:
        with pytest.raises(RuntimeError, match="invalid_base64"):
            await provider.submit(_request())
        with pytest.raises(ValueError, match="artifact_ref_invalid"):
            await provider.download("https://attacker.example/image.png")
    finally:
        await client.aclose()


def test_base_url_and_gpt_image_size_validation_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="base_url_not_allowed"):
        OpenAICompatibleImageProvider(
            provider="timicc",
            api_key="test-key",
            base_url="https://attacker.example/v1",
            model="gpt-image-2",
            allowed_hosts={"timicc.com"},
            staging_root=tmp_path,
        )
    with pytest.raises(ImageProviderSubmissionRejected, match="size_unsupported"):
        OpenAICompatibleImageProvider(
            provider="timicc",
            api_key="test-key",
            base_url="https://timicc.com",
            model="gpt-image-2",
            allowed_hosts={"timicc.com"},
            staging_root=tmp_path,
            default_size="1025x1024",
        )
