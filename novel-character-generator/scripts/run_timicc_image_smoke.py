from __future__ import annotations

import asyncio
import hashlib
import json
import struct
import time
from datetime import UTC, datetime
from pathlib import Path

from run_dashscope_image_smoke import _expected_field_spec

from novel_character_generator.application.ports.image_generation import ImageSubmitRequest
from novel_character_generator.infrastructure.image.openai_compatible import (
    OpenAICompatibleImageProvider,
)
from novel_character_generator.infrastructure.image.prompting import (
    create_image_prompt_renderer,
)
from novel_character_generator.settings import Settings


async def _run() -> Path:
    settings = Settings()
    if settings.timicc_api_key is None:
        raise RuntimeError(
            "TIMICC_API_KEY is required; store it in the local .env and do not pass it "
            "on the command line"
        )
    renderer = create_image_prompt_renderer(settings.image_prompt_renderer)
    provider = OpenAICompatibleImageProvider(
        provider="timicc",
        api_key=settings.timicc_api_key.get_secret_value(),
        base_url=settings.timicc_base_url,
        model=settings.timicc_image_model,
        allowed_hosts={"timicc.com"},
        staging_root=settings.timicc_image_staging_root,
        quality=settings.timicc_image_quality,
        default_size=settings.timicc_image_default_size,
        timeout_seconds=settings.timicc_timeout_seconds,
        prompt_renderer=renderer,
    )
    render_spec = _expected_field_spec()
    rendered_prompt = renderer.render(render_spec)
    started = time.perf_counter()
    try:
        submission = await provider.submit(
            ImageSubmitRequest(
                context_hash="0" * 64,
                workflow_profile="gpt-image-character-baseline-candidate",
                workflow_version="1",
                candidate_index=0,
                seed=270827,
                render_spec=render_spec,
            )
        )
        image = await provider.download(submission.artifact_refs[0])
    finally:
        await provider.close()
    latency_seconds = round(time.perf_counter() - started, 3)
    actual_width, actual_height = _png_dimensions(image)
    return await asyncio.to_thread(
        _save_image,
        image,
        {
            "provider": "timicc",
            "model": settings.timicc_image_model,
            "provider_request_id": submission.provider_request_id,
            "quality": settings.timicc_image_quality,
            "requested_size": "1328x1328",
            "actual_size": f"{actual_width}x{actual_height}",
            "size_match": (actual_width, actual_height) == (1328, 1328),
            "requested_seed": 270827,
            "seed_supported_by_provider": False,
            "spec_hash": render_spec.spec_hash,
            "latency_seconds": latency_seconds,
            "rendered_prompt": rendered_prompt.model_dump(mode="json"),
        },
    )


def _png_dimensions(image: bytes) -> tuple[int, int]:
    if len(image) < 24 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("timicc_result_is_not_png")
    return struct.unpack(">II", image[16:24])


def _save_image(image: bytes, prompt_record: dict[str, object]) -> Path:
    output_dir = Path("data/diagnostics/live-image-smoke")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = output_dir / f"baseline-candidate-gpt-image-2-v1-{timestamp}.png"
    output.write_bytes(image)
    prompt_record["image_sha256"] = hashlib.sha256(image).hexdigest()
    output.with_suffix(".prompt.json").write_text(
        json.dumps(prompt_record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output.resolve()


def main() -> None:
    output = asyncio.run(_run())
    print(f"saved={output}")


if __name__ == "__main__":
    main()
