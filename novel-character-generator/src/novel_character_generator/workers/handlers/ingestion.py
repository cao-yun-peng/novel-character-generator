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
from novel_character_generator.infrastructure.db.repositories.retrieval import RetrievalRepository
from novel_character_generator.workers.task_claim import (
    complete_step,
    complete_step_and_enqueue,
    mark_cancelled,
    record_step_error,
    start_step,
)


async def process_ingestion_run(
    session: AsyncSession,
    artifact_store: ArtifactStore,
    run_id: UUID,
    *,
    target_tokens: int,
    overlap_tokens: int = 0,
    max_attempts: int = 3,
) -> None:
    repository = IngestionRepository(session)
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type not in {"text_ingestion", "text_analysis"}:
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
    if step.status not in {"queued", "retry_scheduled", "claimed"}:
        raise ValueError("ingestion_step_not_runnable")
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
    novel_id = run.novel_id
    expected_generation = await start_step(session, step=step, run=run)
    try:
        novel = await repository.get_novel(novel_id)
        document = await repository.latest_document(novel_id)
        document_version = await repository.latest_document_version(novel_id)
        if novel is None or document is None or document_version is None:
            raise RuntimeError("ingestion_source_not_found")
        data = await artifact_store.get(document_version.storage_uri)
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
            document_version=document_version,
            normalized=normalized,
            chapters=chapters,
            chunks=chunks,
        )
        await RetrievalRepository(session).map_passages_to_chunks(document_version.id)
        cursor = {
            "schema_version": "v1",
            "current_chunk_ordinal": len(chunks),
            "completed_step_keys": [step.step_key],
        }
        if run.run_type == "text_analysis":
            await complete_step_and_enqueue(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor=cursor,
                next_step_key="extract_characters",
            )
        else:
            await complete_step(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor=cursor,
            )
    except Exception as error:
        await record_step_error(
            session,
            step_id=step_id,
            run_id=persisted_run_id,
            error_code="ingestion_failed",
            error=error,
            max_attempts=max_attempts,
            expected_generation=expected_generation,
        )
        raise
