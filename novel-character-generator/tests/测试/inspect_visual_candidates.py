r"""Inspect the production visual-observation-v3 contract against a local TXT file."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from novel_character_generator.application.services.visual_candidate_adapter import (  # noqa: E402
    adapt_visual_candidates,
)
from novel_character_generator.domain.entities.document import TextChunk  # noqa: E402
from novel_character_generator.domain.policies.text_processing import (  # noqa: E402
    build_chunks,
    decode_text,
    detect_chapters,
    normalize_text,
)
from novel_character_generator.infrastructure.llm.openai_compatible import (  # noqa: E402
    OpenAICompatibleExtractionProvider,
    build_chunk_extraction_request,
)
from novel_character_generator.workers.main import extraction_provider  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _chunks(path: Path, target_tokens: int) -> list[TextChunk]:
    decoded, _ = decode_text(path.read_bytes())
    normalized = normalize_text(decoded)
    chapters = detect_chapters(normalized.text)
    return list(build_chunks(normalized, chapters, target_tokens=target_tokens))


def _parse_chunk_ordinals(value: str) -> set[int]:
    try:
        ordinals = {int(item.strip()) for item in value.split(",") if item.strip()}
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "chunk ordinals must be comma-separated integers"
        ) from error
    if not ordinals or min(ordinals) < 0:
        raise argparse.ArgumentTypeError("chunk ordinals must be non-negative")
    return ordinals


async def inspect(
    source: Path,
    *,
    output_dir: Path,
    target_tokens: int,
    prompt_only: bool,
    max_chunks: int | None,
    chunk_ordinals: set[int] | None,
) -> None:
    provider = extraction_provider()
    chunks = _chunks(source, target_tokens)
    if chunk_ordinals is not None:
        available = {chunk.ordinal for chunk in chunks}
        missing = sorted(chunk_ordinals - available)
        if missing:
            raise ValueError(f"unknown_chunk_ordinals:{','.join(map(str, missing))}")
        chunks = [chunk for chunk in chunks if chunk.ordinal in chunk_ordinals]
    elif max_chunks is not None:
        chunks = chunks[:max_chunks]
    await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)
    records: list[dict[str, object]] = []

    for chunk in chunks:
        content = str(chunk.content)
        record: dict[str, object] = {
            "chunk_ordinal": chunk.ordinal,
            "chapter_ordinal": chunk.chapter_ordinal,
            "content": content,
        }
        if isinstance(provider, OpenAICompatibleExtractionProvider):
            record["request_body"] = build_chunk_extraction_request(
                content,
                model=provider.model,
                wire_api=provider.wire_api,
                thinking_enabled=provider.thinking_enabled,
                reasoning_effort=provider.reasoning_effort,
                max_output_tokens=provider.max_output_tokens,
            )
        if prompt_only:
            records.append(record)
            continue

        if isinstance(provider, OpenAICompatibleExtractionProvider):
            raw = await provider.request_chunk_raw(content)
            candidates = provider.process_raw_response(raw)
            record["provider_metadata"] = raw.metadata.model_dump(mode="json")
            record["raw_response"] = raw.response_payload
        else:
            candidates = await provider.extract_chunk(content)
        grounded = adapt_visual_candidates(content, candidates)
        record["visual_candidates"] = candidates.model_dump(mode="json")
        record["grounded_visual_result"] = grounded.model_dump(mode="json")
        records.append(record)

    suffix = "prompt" if prompt_only else "result"
    destination = output_dir / f"{source.stem}.visual-v3.{suffix}.json"
    _write_json(
        destination,
        {
            "schema_version": "visual-observation-v3",
            "source": str(source),
            "provider_version": provider.version,
            "chunk_count": len(records),
            "chunks": records,
        },
    )
    print(destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/diagnostics"))
    parser.add_argument("--chunk-tokens", type=int, default=1_000)
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument(
        "--chunk-ordinals",
        type=_parse_chunk_ordinals,
        help="comma-separated zero-based chunk ordinals; mutually exclusive with --max-chunks",
    )
    parser.add_argument("--prompt-only", action="store_true")
    args = parser.parse_args()
    if args.max_chunks is not None and args.chunk_ordinals is not None:
        parser.error("--max-chunks and --chunk-ordinals are mutually exclusive")
    asyncio.run(
        inspect(
            args.source,
            output_dir=args.output_dir,
            target_tokens=args.chunk_tokens,
            prompt_only=args.prompt_only,
            max_chunks=args.max_chunks,
            chunk_ordinals=args.chunk_ordinals,
        )
    )


if __name__ == "__main__":
    main()
