from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.application.services.run_service import RunService
from novel_character_generator.infrastructure.db.orm import (
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterLifePhaseORM,
    CharacterORM,
    CharacterRenderProfileORM,
    FeatureObservationORM,
    ObservationScopeBindingORM,
    PipelineRunORM,
    PipelineStepORM,
    RunEventORM,
    TemporalSignalORM,
    TextChunkORM,
)
from novel_character_generator.infrastructure.db.session import (
    dispose_engine,
    session_factory,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.main import run_once


def _token_usage(value: Any) -> tuple[int, int, int]:
    if isinstance(value, dict):
        prompt = int(value.get("prompt_tokens", value.get("input_tokens", 0)) or 0)
        completion = int(value.get("completion_tokens", value.get("output_tokens", 0)) or 0)
        total = int(value.get("total_tokens", 0) or 0)
        for child in value.values():
            child_prompt, child_completion, child_total = _token_usage(child)
            prompt += child_prompt
            completion += child_completion
            total += child_total
        return prompt, completion, total
    if isinstance(value, list):
        prompt = completion = total = 0
        for child in value:
            child_prompt, child_completion, child_total = _token_usage(child)
            prompt += child_prompt
            completion += child_completion
            total += child_total
        return prompt, completion, total
    return 0, 0, 0


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


async def main() -> None:
    source_path = Path(os.environ["DIAGNOSTIC_SOURCE_PATH"])
    output_path = Path(os.environ["DIAGNOSTIC_OUTPUT_PATH"])
    settings = get_settings()
    source_bytes = await asyncio.to_thread(source_path.read_bytes)

    existing_run_id = os.environ.get("DIAGNOSTIC_RUN_ID")
    if existing_run_id:
        run_id = UUID(existing_run_id)
        async with session_factory() as session:
            run = await session.get(PipelineRunORM, run_id)
            if run is None:
                raise RuntimeError("analysis_run_missing")
            novel_id = run.novel_id
            if run.status == "failed" and os.environ.get("DIAGNOSTIC_ALLOW_RETRY") == "1":
                retried = await RunService(session).retry(
                    run_id,
                    max_attempts=settings.max_task_attempts,
                )
                if retried is None:
                    raise RuntimeError("analysis_run_retry_failed")
        print(f"RUN_RESUMED novel_id={novel_id} run_id={run_id}", flush=True)
    else:
        async with session_factory() as session:
            service = IngestionService(session, LocalArtifactStore(settings.artifact_local_root))
            novel = await service.upload(filename=source_path.name, data=source_bytes)
            run = await service.create_analysis_run(novel.id, "douluo-r3-real-20260827")
            if run is None:
                raise RuntimeError("analysis_run_not_created")
            novel_id = novel.id
            run_id = run.id
        print(f"RUN_CREATED novel_id={novel_id} run_id={run_id}", flush=True)

    for _ in range(8):
        async with session_factory() as session:
            run = await session.get(PipelineRunORM, run_id)
            if run is None:
                raise RuntimeError("analysis_run_missing")
            if run.status in {"succeeded", "failed", "cancelled"}:
                break
        await run_once(run_id)
        async with session_factory() as session:
            run = await session.get(PipelineRunORM, run_id)
            steps = list(
                await session.scalars(
                    select(PipelineStepORM)
                    .where(PipelineStepORM.run_id == run_id)
                    .order_by(PipelineStepORM.created_at)
                )
            )
            print(
                "STEP_STATE "
                + json.dumps(
                    {
                        "run_status": run.status if run is not None else "missing",
                        "steps": [
                            {
                                "step": item.step_key,
                                "status": item.status,
                                "cursor": item.cursor,
                                "error_code": item.error_code,
                            }
                            for item in steps
                        ],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    async with session_factory() as session:
        run = await session.get(PipelineRunORM, run_id)
        if run is None:
            raise RuntimeError("analysis_run_missing")
        steps = list(
            await session.scalars(
                select(PipelineStepORM)
                .where(PipelineStepORM.run_id == run_id)
                .order_by(PipelineStepORM.created_at)
            )
        )
        characters = list(
            await session.scalars(
                select(CharacterORM)
                .where(CharacterORM.novel_id == novel_id)
                .order_by(CharacterORM.canonical_name, CharacterORM.id)
            )
        )
        character_summaries: list[dict[str, Any]] = []
        for character in characters:
            active_observations = int(
                await session.scalar(
                    select(func.count())
                    .select_from(FeatureObservationORM)
                    .where(
                        FeatureObservationORM.character_id == character.id,
                        FeatureObservationORM.record_status == "active",
                    )
                )
                or 0
            )
            pending_observations = int(
                await session.scalar(
                    select(func.count())
                    .select_from(FeatureObservationORM)
                    .where(
                        FeatureObservationORM.character_id == character.id,
                        FeatureObservationORM.record_status == "pending",
                    )
                )
                or 0
            )
            phases = list(
                await session.scalars(
                    select(CharacterLifePhaseORM)
                    .where(
                        CharacterLifePhaseORM.character_id == character.id,
                        CharacterLifePhaseORM.record_status == "active",
                    )
                    .order_by(CharacterLifePhaseORM.phase_order, CharacterLifePhaseORM.id)
                )
            )
            character_summaries.append(
                {
                    "id": str(character.id),
                    "name": character.canonical_name,
                    "active_observations": active_observations,
                    "pending_observations": pending_observations,
                    "phases": [
                        {
                            "key": phase.phase_key,
                            "label": phase.label,
                            "start_chapter": phase.start_chapter_ordinal,
                            "end_chapter": phase.end_chapter_ordinal,
                            "confidence": phase.confidence,
                            "status": phase.status,
                        }
                        for phase in phases
                    ],
                }
            )

        events = list(
            await session.scalars(
                select(RunEventORM)
                .where(RunEventORM.run_id == run_id)
                .order_by(RunEventORM.sequence)
            )
        )
        prompt_tokens = completion_tokens = total_tokens = 0
        for event in events:
            event_prompt, event_completion, event_total = _token_usage(event.payload)
            prompt_tokens += event_prompt
            completion_tokens += event_completion
            total_tokens += event_total

        signal_statuses = Counter(
            await session.scalars(
                select(TemporalSignalORM.resolution_status).where(
                    TemporalSignalORM.run_id == run_id
                )
            )
        )
        signal_kinds = Counter(
            await session.scalars(
                select(TemporalSignalORM.kind).where(TemporalSignalORM.run_id == run_id)
            )
        )
        binding_statuses = Counter(
            await session.scalars(
                select(ObservationScopeBindingORM.status).where(
                    ObservationScopeBindingORM.run_id == run_id,
                    ObservationScopeBindingORM.record_status == "active",
                )
            )
        )
        summary = {
            "source": {
                "name": source_path.name,
                "bytes": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            },
            "provider": {
                "name": settings.llm_provider,
                "model": settings.llm_model,
            },
            "novel_id": str(novel_id),
            "run_id": str(run_id),
            "run_status": run.status,
            "steps": [
                {
                    "step": item.step_key,
                    "status": item.status,
                    "error_code": item.error_code,
                    "error_message": item.error_message,
                    "cursor": item.cursor,
                }
                for item in steps
            ],
            "counts": {
                "chunks": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(TextChunkORM)
                        .where(TextChunkORM.novel_id == novel_id)
                    )
                    or 0
                ),
                "characters": len(characters),
                "active_observations": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(FeatureObservationORM)
                        .where(
                            FeatureObservationORM.extraction_run_id == run_id,
                            FeatureObservationORM.record_status == "active",
                        )
                    )
                    or 0
                ),
                "pending_observations": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(FeatureObservationORM)
                        .where(
                            FeatureObservationORM.extraction_run_id == run_id,
                            FeatureObservationORM.record_status == "pending",
                        )
                    )
                    or 0
                ),
                "temporal_signals": sum(signal_statuses.values()),
                "life_phases": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(CharacterLifePhaseORM)
                        .where(CharacterLifePhaseORM.run_id == run_id)
                    )
                    or 0
                ),
                "appearance_states": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(CharacterAppearanceStateORM)
                        .where(CharacterAppearanceStateORM.created_by_run_id == run_id)
                    )
                    or 0
                ),
                "render_profiles": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(CharacterRenderProfileORM)
                        .where(CharacterRenderProfileORM.aggregation_run_id == run_id)
                    )
                    or 0
                ),
                "conflicts": int(
                    await session.scalar(
                        select(func.count())
                        .select_from(CharacterConflictORM)
                        .join(
                            CharacterORM,
                            CharacterConflictORM.character_id == CharacterORM.id,
                        )
                        .where(CharacterORM.novel_id == novel_id)
                    )
                    or 0
                ),
            },
            "temporal_signal_statuses": dict(signal_statuses),
            "temporal_signal_kinds": dict(signal_kinds),
            "scope_binding_statuses": dict(binding_statuses),
            "characters": character_summaries,
            "event_type_counts": dict(Counter(event.event_type for event in events)),
            "recorded_token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "note": (
                    "Summed from persisted RunEvent payload fields; zero means provider "
                    "usage was not recorded."
                ),
            },
        }

    await asyncio.to_thread(_write_summary, output_path, summary)
    print(f"SUMMARY_WRITTEN {output_path}", flush=True)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    await dispose_engine()
    if summary["run_status"] != "succeeded":
        raise RuntimeError(f"analysis_run_{summary['run_status']}")


if __name__ == "__main__":
    asyncio.run(main())
