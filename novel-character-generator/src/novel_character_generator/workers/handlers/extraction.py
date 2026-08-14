from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.extraction import ExtractionProvider
from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.db.repositories.extraction import ExtractionRepository
from novel_character_generator.workers.task_claim import (
    checkpoint_step,
    complete_step,
    mark_cancelled,
    record_step_error,
    start_step,
)


async def process_extraction_run(
    session: AsyncSession,
    provider: ExtractionProvider,
    run_id: UUID,
    *,
    max_attempts: int = 3,
    lease_seconds: int = 120,
) -> None:
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type not in {"character_extraction", "text_analysis"}:
        raise ValueError("extraction_run_not_found")
    step = await session.scalar(
        select(PipelineStepORM).where(
            PipelineStepORM.run_id == run_id,
            PipelineStepORM.step_key == "extract_characters",
        )
    )
    if step is None:
        raise RuntimeError("extraction_step_not_found")
    if step.status == "succeeded":
        return
    if step.status not in {"queued", "retry_scheduled", "claimed"}:
        raise ValueError("extraction_step_not_runnable")
    if run.cancel_requested:
        await mark_cancelled(
            session,
            step=step,
            run=run,
            expected_generation=step.lease_generation,
        )
        return
    step_id = step.id
    persisted_run_id = run.id
    expected_generation = await start_step(session, step=step, run=run)
    try:
        repository = ExtractionRepository(session)
        document = await repository.source_document(run.novel_id)
        normalization_map = await repository.normalization_map(document.id)
        timeline = await repository.canonical_timeline(run.novel_id)
        chunks = await repository.chunks(run.novel_id)
        cursor = step.cursor or {}
        start_ordinal = int(cursor.get("current_chunk_ordinal", 0))
        await session.commit()

        for chunk in chunks:
            if chunk.ordinal < start_ordinal:
                continue
            await session.refresh(run, attribute_names=["cancel_requested"])
            if run.cancel_requested:
                await mark_cancelled(
                    session,
                    step=step,
                    run=run,
                    expected_generation=expected_generation,
                )
                return
            # No database transaction is held while waiting for the provider.
            await session.commit()
            result = await provider.extract_chunk(chunk.content)
            await repository.persist_result(
                run=run,
                chunk=chunk,
                document=document,
                normalization_map=normalization_map,
                timeline=timeline,
                result=result,
                extractor_version=provider.version,
            )
            await checkpoint_step(
                session,
                step=step,
                expected_generation=expected_generation,
                cursor={
                    "schema_version": "v1",
                    "current_chunk_ordinal": chunk.ordinal + 1,
                    "completed_step_keys": [],
                },
                lease_seconds=lease_seconds,
            )
        await complete_step(
            session,
            step=step,
            run=run,
            expected_generation=expected_generation,
            cursor={
                "schema_version": "v1",
                "current_chunk_ordinal": len(chunks),
                "completed_step_keys": [step.step_key],
            },
        )
    except Exception as error:
        await record_step_error(
            session,
            step_id=step_id,
            run_id=persisted_run_id,
            error_code="extraction_failed",
            error=error,
            max_attempts=max_attempts,
            expected_generation=expected_generation,
        )
        raise
