from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.artifact_store import ArtifactStore
from novel_character_generator.application.ports.embedding import EmbeddingPort
from novel_character_generator.application.ports.vector_store import VectorPoint, VectorStorePort
from novel_character_generator.domain.policies.retrieval import (
    ChineseSearchTermBuilder,
    build_retrieval_passages,
)
from novel_character_generator.domain.policies.text_processing import (
    decode_text,
    detect_chapters,
    normalize_text,
)
from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.db.repositories.retrieval import RetrievalRepository
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event
from novel_character_generator.workers.task_claim import (
    checkpoint_step,
    complete_step,
    mark_cancelled,
    record_step_error,
    start_step,
)


async def process_retrieval_indexing_run(
    session: AsyncSession,
    artifact_store: ArtifactStore,
    run_id: UUID,
    *,
    target_tokens: int,
    overlap_tokens: int,
    embedding_provider: EmbeddingPort | None = None,
    vector_store: VectorStorePort | None = None,
    embedding_batch_size: int = 16,
    lease_seconds: int = 240,
    embedding_enabled: bool | None = None,
    max_attempts: int = 3,
) -> None:
    repository = RetrievalRepository(session)
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type != "source_indexing":
        raise ValueError("source_indexing_run_not_found")
    step = await session.scalar(
        select(PipelineStepORM).where(
            PipelineStepORM.run_id == run_id,
            PipelineStepORM.step_key == "build_retrieval_index",
        )
    )
    if step is None:
        raise RuntimeError("retrieval_indexing_step_not_found")
    if step.status == "succeeded":
        return
    if step.status not in {"queued", "retry_scheduled", "claimed"}:
        raise ValueError("retrieval_indexing_step_not_runnable")
    if run.cancel_requested:
        await mark_cancelled(
            session,
            step=step,
            run=run,
            expected_generation=step.lease_generation,
        )
        return

    expected_generation = await start_step(session, step=step, run=run)
    build = await repository.get_build_for_run(run_id)
    if build is None:
        raise RuntimeError("retrieval_index_build_not_found")
    step_id = step.id
    try:
        await repository.mark_build(build, status="building")
        await append_run_event(
            session,
            run_id=run.id,
            event_type="retrieval.index.started",
            payload={
                "retrieval_index_build_id": str(build.id),
                "source_document_version_id": str(build.source_document_version_id),
                "index_version": build.index_version,
            },
        )
        await session.commit()

        source = await repository.get_source(build.source_document_version_id)
        if source is None:
            raise RuntimeError("retrieval_index_source_not_found")
        _, document_version = source
        data = await artifact_store.get(document_version.storage_uri)
        original, _ = decode_text(data)
        normalized = normalize_text(original)
        chapters = detect_chapters(normalized.text)
        passages = build_retrieval_passages(
            normalized,
            chapters,
            build_id=build.id,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )
        term_builder = ChineseSearchTermBuilder()
        terms = {passage.id: term_builder.build(passage.content) for passage in passages}
        await repository.persist_passages(build=build, passages=passages, search_terms=terms)
        adapters_configured = embedding_provider is not None and vector_store is not None
        explicitly_enabled = embedding_enabled is True
        if (embedding_provider is None) != (vector_store is None):
            raise RuntimeError("retrieval_vector_adapter_configuration_incomplete")
        await repository.mark_build(
            build,
            status="building" if adapters_configured else "degraded_lexical_only",
            error_summary=None if adapters_configured else "embedding_provider_disabled",
        )
        await append_run_event(
            session,
            run_id=run.id,
            event_type="retrieval.index.lexical_ready",
            payload={
                "retrieval_index_build_id": str(build.id),
                "passage_count": len(passages),
                "lexical_profile_version": build.lexical_profile_version,
                "vector_ready": False,
                "vector_build_configured": adapters_configured,
            },
        )
        await session.commit()

        if adapters_configured:
            assert embedding_provider is not None
            assert vector_store is not None
            profile = embedding_provider.profile
            if build.embedding_profile_version != profile.profile_version:
                raise ValueError("retrieval_embedding_profile_mismatch")
            if profile.dimension != vector_store.dimension:
                raise ValueError("retrieval_vector_dimension_mismatch")
            await vector_store.ensure_collection()
            stored_passages = await repository.list_passages(build.id)
            completed_ids = await repository.completed_embedding_ids(
                build_id=build.id,
                embedding_profile_version=profile.profile_version,
            )
            remaining = [passage for passage in stored_passages if passage.id not in completed_ids]
            for batch_start in range(0, len(remaining), embedding_batch_size):
                batch_passages = remaining[batch_start : batch_start + embedding_batch_size]
                embedded = await embedding_provider.embed_documents(
                    [passage.content for passage in batch_passages]
                )
                if len(embedded.vectors) != len(batch_passages):
                    raise RuntimeError("embedding_response_count_mismatch")
                await vector_store.upsert(
                    [
                        VectorPoint(
                            id=passage.id,
                            vector=vector,
                            payload={
                                "source_document_version_id": str(
                                    build.source_document_version_id
                                ),
                                "retrieval_index_build_id": str(build.id),
                                "chapter_ordinal": passage.chapter_ordinal,
                                "ordinal": passage.ordinal,
                                "content_hash": passage.content_hash,
                            },
                        )
                        for passage, vector in zip(batch_passages, embedded.vectors, strict=True)
                    ]
                )
                await repository.record_ready_embeddings(
                    passages=batch_passages,
                    embedding_profile_version=profile.profile_version,
                    dimension=profile.dimension,
                    qdrant_collection=vector_store.collection_name,
                )
                completed_ids.update(passage.id for passage in batch_passages)
                await checkpoint_step(
                    session,
                    step=step,
                    expected_generation=expected_generation,
                    lease_seconds=lease_seconds,
                    cursor={
                        "schema_version": "v1",
                        "retrieval_index_build_id": str(build.id),
                        "passage_count": len(stored_passages),
                        "embedded_passage_count": len(completed_ids),
                    },
                )
            await repository.mark_build(build, status="ready", error_summary=None)
            await append_run_event(
                session,
                run_id=run.id,
                event_type="retrieval.index.ready",
                payload={
                    "retrieval_index_build_id": str(build.id),
                    "passage_count": len(stored_passages),
                    "embedding_profile_version": profile.profile_version,
                    "dimension": profile.dimension,
                    "qdrant_collection": vector_store.collection_name,
                },
            )
            await session.commit()
        elif explicitly_enabled:
            raise RuntimeError("retrieval_vector_adapter_configuration_incomplete")

        await complete_step(
            session,
            step=step,
            run=run,
            expected_generation=expected_generation,
            cursor={
                "schema_version": "v1",
                "retrieval_index_build_id": str(build.id),
                "passage_count": len(passages),
                "index_status": "ready" if adapters_configured else "degraded_lexical_only",
                "completed_step_keys": [step.step_key],
            },
        )
    except Exception as error:
        await record_step_error(
            session,
            step_id=step_id,
            run_id=run.id,
            error_code="retrieval_indexing_failed",
            error=error,
            max_attempts=max_attempts,
            expected_generation=expected_generation,
        )
        build = await repository.get_build_for_run(run_id)
        if build is not None and build.status != "degraded_lexical_only":
            await repository.mark_build(build, status="failed", error_summary=str(error)[:2_000])
        await append_run_event(
            session,
            run_id=run.id,
            event_type="retrieval.index.failed",
            payload={"error_code": "retrieval_indexing_failed"},
        )
        await session.commit()
        raise
