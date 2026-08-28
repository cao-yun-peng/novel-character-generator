from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from novel_character_generator.application.ports.image_generation import ImageSubmitRequest
from novel_character_generator.domain.entities.image import ImageRenderSpec
from novel_character_generator.infrastructure.image.dashscope import DashScopeImageProvider
from novel_character_generator.infrastructure.image.prompting import (
    create_image_prompt_renderer,
)
from novel_character_generator.settings import Settings


def _expected_field_spec() -> ImageRenderSpec:
    """A bounded expected-field candidate without inferred personality or facial facts."""
    positive_paths = [
        "hair.color",
        "hair.length",
        "skin.color",
        "age",
        "age_stage",
        "body.build",
        "clothing.style",
        "pose.body",
        "gaze",
        "environment.location",
        "environment.time",
        "environment.background",
        "art_direction.medium",
        "art_direction.lighting",
        "composition.shot",
    ]
    negative_constraints = [
        "文字",
        "水印",
        "现代服装",
        "成年人体型",
        "夸张肌肉",
        "肢体畸形",
        "多余手指",
        "模糊面部",
    ]
    novel_asserted_paths = set(positive_paths[:7])
    source_map = {
        path: [
            {
                "source_kind": (
                    "novel_asserted" if path in novel_asserted_paths else "workflow_default"
                )
            }
        ]
        for path in [
            *positive_paths,
            *[
                f"negative_constraints[{index}]"
                for index in range(len(negative_constraints))
            ],
        ]
    }
    payload: dict[str, object] = {
        "schema_version": "v1",
        "generation_mode": "character_design",
        "identity_prompt_block": [
            "hair.color: black",
            "hair.length: short",
            "skin.color: 健康的小麦色",
        ],
        "stage_prompt_block": [
            "age: 五、六岁",
            "age_stage: childhood",
            "body.build: 瘦小",
        ],
        "outfit_prompt_block": ["clothing.style: 朴素的灰色旧布衣"],
        "performance_prompt_block": [
            "pose.body: 安静坐在山石上",
            "gaze: 望向东方晨光",
        ],
        "environment_prompt_block": [
            "environment.location: 山顶",
            "environment.time: 黎明",
            "environment.background: 远处群山与薄雾",
        ],
        "art_direction_prompt_block": [
            "art_direction.medium: 东方玄幻小说角色概念插画",
            "art_direction.lighting: 柔和晨光",
            "composition.shot: full body",
        ],
        "negative_constraints": negative_constraints,
        "output_parameters": {"size": "1328*1328"},
        "source_map": source_map,
        "compiler_version": "image-render-compiler-v1",
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload["spec_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    return ImageRenderSpec.model_validate(payload)


async def _run(max_wait_seconds: int) -> Path:
    settings = Settings()
    if settings.dashscope_api_key is None or not settings.dashscope_base_url:
        raise RuntimeError(
            "DASHSCOPE_API_KEY and the region-specific DASHSCOPE_BASE_URL are required"
        )
    prompt_renderer = create_image_prompt_renderer(settings.image_prompt_renderer)
    provider = DashScopeImageProvider(
        api_key=settings.dashscope_api_key.get_secret_value(),
        base_url=settings.dashscope_base_url,
        model=settings.dashscope_image_model,
        default_size=settings.dashscope_image_default_size,
        timeout_seconds=settings.dashscope_timeout_seconds,
        prompt_renderer=prompt_renderer,
    )
    render_spec = _expected_field_spec()
    rendered_prompt = prompt_renderer.render(render_spec)
    try:
        submission = await provider.submit(
            ImageSubmitRequest(
                context_hash="0" * 64,
                workflow_profile="qwen-character-baseline-candidate",
                workflow_version="1",
                candidate_index=0,
                seed=270827,
                render_spec=render_spec,
            )
        )
        print(f"submitted task_id={submission.provider_request_id}", flush=True)
        deadline = asyncio.get_running_loop().time() + max_wait_seconds
        while True:
            remote = await provider.query(submission.provider_request_id)
            print(f"task_status={remote.status}", flush=True)
            if remote.status == "failed":
                raise RuntimeError(remote.error_code or "dashscope_image_failed")
            if remote.status == "succeeded" and remote.artifact_refs:
                image = await provider.download(remote.artifact_refs[0])
                if not image.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise RuntimeError("dashscope_result_is_not_png")
                return await asyncio.to_thread(
                    _save_image,
                    image,
                    {
                        "model": settings.dashscope_image_model,
                        "provider_request_id": submission.provider_request_id,
                        "seed": 270827,
                        "size": "1328*1328",
                        "spec_hash": render_spec.spec_hash,
                        "rendered_prompt": rendered_prompt.model_dump(mode="json"),
                    },
                )
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("dashscope_image_smoke_timed_out")
            await asyncio.sleep(settings.image_poll_interval_seconds)
    finally:
        await provider.close()


def _save_image(image: bytes, prompt_record: dict[str, object]) -> Path:
    output_dir = Path("data/diagnostics/live-image-smoke")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = output_dir / f"baseline-candidate-v1-{timestamp}.png"
    output.write_bytes(image)
    output.with_suffix(".prompt.json").write_text(
        json.dumps(prompt_record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit exactly one expected-field image to DashScope."
    )
    parser.add_argument("--max-wait-seconds", type=int, default=600)
    args = parser.parse_args()
    output = asyncio.run(_run(args.max_wait_seconds))
    print(f"saved={output}")


if __name__ == "__main__":
    main()
