import argparse
import asyncio
import logging
import os
import socket
from uuid import UUID

from sqlalchemy import case, select

from novel_character_generator.application.ports.embedding import EmbeddingProfile
from novel_character_generator.application.ports.visual_enrichment import (
    VisualEnrichmentProvider,
)
from novel_character_generator.application.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.db.session import session_factory
from novel_character_generator.infrastructure.embedding.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)
from novel_character_generator.infrastructure.llm.mock import MockExtractionProvider
from novel_character_generator.infrastructure.llm.openai_compatible import (
    OpenAICompatibleExtractionProvider,
)
from novel_character_generator.infrastructure.llm.visual_enrichment import (
    MockVisualEnrichmentProvider,
    OpenAICompatibleVisualEnrichmentProvider,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.infrastructure.vector.qdrant_local import (
    QdrantLocalVectorStore,
    qdrant_collection_name,
)
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.handlers.appearance_aggregation import (
    process_appearance_aggregation_run,
)
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run
from novel_character_generator.workers.handlers.retrieval_indexing import (
    process_retrieval_indexing_run,
)
from novel_character_generator.workers.handlers.visual_enrichment import (
    process_visual_enrichment_run,
)
from novel_character_generator.workers.task_claim import claim_next_step

logger = logging.getLogger(__name__)


def extraction_provider() -> MockExtractionProvider | OpenAICompatibleExtractionProvider:
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockExtractionProvider()
    assert settings.llm_api_key is not None
    assert settings.llm_model is not None
    return OpenAICompatibleExtractionProvider(
        provider=settings.llm_provider,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def visual_enrichment_provider(
) -> VisualEnrichmentProvider:
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockVisualEnrichmentProvider()
    assert settings.llm_api_key is not None
    assert settings.llm_model is not None
    return OpenAICompatibleVisualEnrichmentProvider(
        provider=settings.llm_provider,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        timeout_seconds=settings.visual_enrichment_timeout_seconds,
    )


async def run_once(run_id: UUID, *, step_key: str | None = None) -> None:
    settings = get_settings()
    async with session_factory() as session:
        run = await session.get(PipelineRunORM, run_id)
        if run is None:
            raise ValueError("run_not_found")
        step_query = select(PipelineStepORM).where(
            PipelineStepORM.run_id == run_id,
            PipelineStepORM.status.in_(("queued", "retry_scheduled", "claimed")),
        )
        if step_key is not None:
            step_query = step_query.where(PipelineStepORM.step_key == step_key)
        step = await session.scalar(
            step_query.order_by(
                case((PipelineStepORM.status == "claimed", 0), else_=1),
                PipelineStepORM.created_at,
            )
        )
        if step is None:
            raise ValueError("runnable_step_not_found")
        if step.step_key == "normalize_and_chunk":
            await process_ingestion_run(
                session,
                LocalArtifactStore(settings.artifact_local_root),
                run_id,
                target_tokens=settings.max_chunk_input_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
                max_attempts=settings.max_task_attempts,
            )
        elif step.step_key == "build_retrieval_index":
            if settings.embedding_provider == "disabled":
                await process_retrieval_indexing_run(
                    session,
                    LocalArtifactStore(settings.artifact_local_root),
                    run_id,
                    target_tokens=settings.retrieval_passage_target_tokens,
                    overlap_tokens=settings.retrieval_passage_overlap_tokens,
                    embedding_batch_size=settings.embedding_batch_size,
                    lease_seconds=settings.worker_lease_seconds,
                    max_attempts=settings.max_task_attempts,
                )
            else:
                assert settings.embedding_base_url is not None
                assert settings.embedding_api_key is not None
                assert settings.embedding_model is not None
                assert settings.embedding_dimension is not None
                assert settings.embedding_profile_version is not None
                profile = EmbeddingProfile(
                    provider=settings.embedding_provider,
                    model=settings.embedding_model,
                    model_revision=settings.embedding_model_revision,
                    dimension=settings.embedding_dimension,
                    profile_version=settings.embedding_profile_version,
                    normalization=settings.embedding_normalization,
                    document_prefix=settings.embedding_document_prefix,
                    query_prefix=settings.embedding_query_prefix,
                )
                embedding = OpenAICompatibleEmbeddingProvider(
                    base_url=settings.embedding_base_url,
                    api_key=settings.embedding_api_key.get_secret_value(),
                    profile=profile,
                    timeout_seconds=settings.embedding_timeout_seconds,
                    max_retries=settings.embedding_max_retries,
                )
                vector_store = QdrantLocalVectorStore(
                    path=settings.qdrant_local_path,
                    collection_name=qdrant_collection_name(
                        embedding_profile_version=profile.profile_version,
                        dimension=profile.dimension,
                        index_version=settings.retrieval_index_version,
                    ),
                    dimension=profile.dimension,
                )
                try:
                    await process_retrieval_indexing_run(
                        session,
                        LocalArtifactStore(settings.artifact_local_root),
                        run_id,
                        target_tokens=settings.retrieval_passage_target_tokens,
                        overlap_tokens=settings.retrieval_passage_overlap_tokens,
                        embedding_provider=embedding,
                        vector_store=vector_store,
                        embedding_batch_size=settings.embedding_batch_size,
                        lease_seconds=settings.worker_lease_seconds,
                        max_attempts=settings.max_task_attempts,
                    )
                finally:
                    await embedding.close()
                    await vector_store.close()
        elif step.step_key == "extract_characters":
            await process_extraction_run(
                session,
                extraction_provider(),
                run_id,
                max_attempts=settings.max_task_attempts,
                lease_seconds=settings.worker_lease_seconds,
            )
        elif step.step_key in {
            "plan_visual_retrieval",
            "retrieve_visual_evidence",
            "extract_visual_evidence",
            "persist_visual_evidence",
        }:
            if step.step_key == "retrieve_visual_evidence":
                if settings.embedding_provider == "disabled":
                    raise RuntimeError("visual_enrichment_embedding_provider_required")
                assert settings.embedding_base_url is not None
                assert settings.embedding_api_key is not None
                assert settings.embedding_model is not None
                assert settings.embedding_dimension is not None
                assert settings.embedding_profile_version is not None
                profile = EmbeddingProfile(
                    provider=settings.embedding_provider,
                    model=settings.embedding_model,
                    model_revision=settings.embedding_model_revision,
                    dimension=settings.embedding_dimension,
                    profile_version=settings.embedding_profile_version,
                    normalization=settings.embedding_normalization,
                    document_prefix=settings.embedding_document_prefix,
                    query_prefix=settings.embedding_query_prefix,
                )
                embedding = OpenAICompatibleEmbeddingProvider(
                    base_url=settings.embedding_base_url,
                    api_key=settings.embedding_api_key.get_secret_value(),
                    profile=profile,
                    timeout_seconds=settings.embedding_timeout_seconds,
                    max_retries=settings.embedding_max_retries,
                )
                vector_store = QdrantLocalVectorStore(
                    path=settings.qdrant_local_path,
                    collection_name=qdrant_collection_name(
                        embedding_profile_version=profile.profile_version,
                        dimension=profile.dimension,
                        index_version=settings.retrieval_index_version,
                    ),
                    dimension=profile.dimension,
                )
                try:
                    await process_visual_enrichment_run(
                        session,
                        run_id,
                        retrieval=HybridRetrievalService(session, embedding, vector_store),
                        bm25_top_k=settings.retrieval_bm25_top_k,
                        vector_top_k=settings.retrieval_vector_top_k,
                        rrf_k=settings.retrieval_rrf_k,
                        main_hit_limit=settings.retrieval_main_hit_limit,
                        neighbor_count=settings.retrieval_neighbor_count,
                        max_attempts=settings.max_task_attempts,
                    )
                finally:
                    await embedding.close()
                    await vector_store.close()
            else:
                await process_visual_enrichment_run(
                    session,
                    run_id,
                    provider=(
                        visual_enrichment_provider()
                        if step.step_key == "extract_visual_evidence"
                        else None
                    ),
                    max_attempts=settings.max_task_attempts,
                )
        elif step.step_key == "aggregate_appearance":
            await process_appearance_aggregation_run(
                session,
                run_id,
                max_attempts=settings.max_task_attempts,
                lease_seconds=settings.worker_lease_seconds,
            )
        else:
            raise ValueError("unsupported_step_key")


async def run_worker(*, once: bool, poll_interval: float, worker_id: str) -> None:
    settings = get_settings()
    while True:
        async with session_factory() as session:
            step = await claim_next_step(
                session,
                worker_id=worker_id,
                lease_seconds=settings.worker_lease_seconds,
            )
            if step is not None:
                try:
                    await run_once(step.run_id, step_key=step.step_key)
                except Exception:
                    logger.exception(
                        "task_processing_failed",
                        extra={"run_id": str(step.run_id), "step_id": str(step.id)},
                    )
        if once:
            return
        await asyncio.sleep(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", type=UUID, nargs="?")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument(
        "--worker-id", default=f"{socket.gethostname()}-{os.getpid()}"
    )
    arguments = parser.parse_args()
    if arguments.run_id is not None:
        asyncio.run(run_once(arguments.run_id))
    else:
        asyncio.run(
            run_worker(
                once=arguments.once,
                poll_interval=arguments.poll_interval,
                worker_id=arguments.worker_id,
            )
        )


if __name__ == "__main__":
    main()
