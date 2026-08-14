from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.artifact_store import ArtifactStore
from novel_character_generator.domain.policies.text_processing import (
    build_chunks,
    decode_text,
    detect_chapters,
    normalize_text,
)
from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.db.repositories.ingestion import IngestionRepository


async def process_ingestion_run(
    session: AsyncSession,
    artifact_store: ArtifactStore,
    run_id: UUID,
    *,
    target_tokens: int,
    overlap_tokens: int = 0,
) -> None:
    repository = IngestionRepository(session)
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type != "text_ingestion":
        raise ValueError("ingestion_run_not_found")
    step = await session.scalar(
        select(PipelineStepORM).where(
            PipelineStepORM.run_id == run_id,
            PipelineStepORM.step_key == "normalize_and_chunk",
        )
    )
    if step is None:
        raise RuntimeError("ingestion_step_not_found")
    if step.status == "succeeded":
        return
    if step.status not in {"queued", "retry_scheduled"}:
        raise ValueError("ingestion_step_not_runnable")
    step_id = step.id
    persisted_run_id = run.id
    novel_id = run.novel_id
    now = datetime.now(UTC)
    step.status = "running"
    step.attempt += 1
    step.updated_at = now
    run.status = "running"
    run.updated_at = now
    await session.commit()
    try:
        novel = await repository.get_novel(novel_id)
        document = await repository.latest_document(novel_id)
        if novel is None or document is None:
            raise RuntimeError("ingestion_source_not_found")
        data = await artifact_store.get(document.storage_uri)
        original, _ = decode_text(data)
        normalized = normalize_text(original)
        chapters = detect_chapters(normalized.text)
        chunks = build_chunks(
            normalized,
            chapters,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )
        await repository.persist_processed_text(
            novel=novel,
            document=document,
            normalized=normalized,
            chapters=chapters,
            chunks=chunks,
        )
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
    except Exception:
        await session.rollback()
        failed_step = await session.get(PipelineStepORM, step_id)
        failed_run = await session.get(PipelineRunORM, persisted_run_id)
        if failed_step is not None and failed_run is not None:
            now = datetime.now(UTC)
            failed_step.status = "failed"
            failed_step.error_code = "ingestion_failed"
            failed_step.updated_at = now
            failed_run.status = "failed"
            failed_run.completed_at = now
            failed_run.updated_at = now
            await session.commit()
        raise
