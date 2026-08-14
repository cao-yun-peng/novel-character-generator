from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.extraction import ExtractionProvider
from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.db.repositories.extraction import ExtractionRepository


async def process_extraction_run(
    session: AsyncSession, provider: ExtractionProvider, run_id: UUID
) -> None:
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type != "character_extraction":
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
    if step.status not in {"queued", "retry_scheduled"}:
        raise ValueError("extraction_step_not_runnable")
    now = datetime.now(UTC)
    step.status = "running"
    step.attempt += 1
    step.updated_at = now
    run.status = "running"
    run.updated_at = now
    await session.commit()
    repository = ExtractionRepository(session)
    document = await repository.source_document(run.novel_id)
    timeline = await repository.canonical_timeline(run.novel_id)
    chunks = await repository.chunks(run.novel_id)
    for index, chunk in enumerate(chunks):
        result = await provider.extract_chunk(chunk.content)
        await repository.persist_result(
            run=run,
            chunk=chunk,
            document=document,
            timeline=timeline,
            result=result,
            extractor_version=provider.version,
        )
        step.cursor = {
            "schema_version": "v1",
            "current_chunk_ordinal": index + 1,
            "completed_step_keys": [],
        }
        await session.commit()
    now = datetime.now(UTC)
    step.status = "succeeded"
    step.cursor = {
        "schema_version": "v1",
        "current_chunk_ordinal": len(chunks),
        "completed_step_keys": [step.step_key],
    }
    step.updated_at = now
    run.status = "succeeded"
    run.completed_at = now
    run.updated_at = now
    await session.commit()
