from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.embedding import (
    EmbeddingBatch,
    EmbeddingProfile,
)
from novel_character_generator.application.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.domain.policies.retrieval import ChineseSearchTermBuilder
from novel_character_generator.infrastructure.db.orm import (
    PipelineRunORM,
    RetrievalIndexBuildORM,
    RetrievalPassageChunkSpanORM,
    RetrievalPassageEmbeddingORM,
    RetrievalPassageORM,
)
from novel_character_generator.infrastructure.db.repositories.retrieval import RetrievalRepository
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.infrastructure.vector.qdrant_local import (
    QdrantLocalVectorStore,
    qdrant_collection_name,
)
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run
from novel_character_generator.workers.handlers.retrieval_indexing import (
    process_retrieval_indexing_run,
)


class RecoveringEmbeddingProvider:
    def __init__(self) -> None:
        self._profile = EmbeddingProfile(
            provider="test",
            model="deterministic",
            model_revision="r1",
            dimension=3,
            profile_version="test-embedding-v1",
            normalization="l2",
            document_prefix="passage: ",
            query_prefix="query: ",
        )
        self.document_calls: list[list[str]] = []
        self._failed_once = False

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    @staticmethod
    def _vector(text: str) -> list[float]:
        if "白衣" in text or "服装" in text:
            return [1.0, 0.0, 0.0]
        if "黑发" in text or "头发" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    async def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        self.document_calls.append(list(texts))
        if len(self.document_calls) == 2 and not self._failed_once:
            self._failed_once = True
            raise RuntimeError("temporary_embedding_failure")
        return EmbeddingBatch(vectors=[self._vector(text) for text in texts])

    async def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(vectors=[self._vector(text) for text in texts])

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_upload_builds_lexical_index_and_maps_passages_to_chunks(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "retrieval.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    content = (
        "第一章 初见\n"
        + "萧炎站在门边。她微微垂首，乌黑的长发沿着白衣滑落。" * 80
    ).encode()

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="检索测试.txt", data=content)
        build = await session.scalar(select(RetrievalIndexBuildORM))
        assert build is not None and build.pipeline_run_id is not None
        indexing_run = await session.get(PipelineRunORM, build.pipeline_run_id)
        assert indexing_run is not None
        assert indexing_run.run_type == "source_indexing"

        await process_retrieval_indexing_run(
            session,
            store,
            indexing_run.id,
            target_tokens=1_000,
            overlap_tokens=100,
            embedding_enabled=False,
        )
        await session.refresh(build)
        assert build.status == "degraded_lexical_only"
        assert build.error_summary == "embedding_provider_disabled"

        term_builder = ChineseSearchTermBuilder(entity_terms=["萧炎"])
        hits = await RetrievalRepository(session).search_bm25(
            build_id=build.id,
            fts_query=term_builder.query("萧炎 白衣 长发"),
        )
        assert hits
        assert "白衣" in hits[0][0].content

        ingestion_run = await service.create_run(novel.id, "retrieval-mapping-ingestion")
        assert ingestion_run is not None
        await process_ingestion_run(session, store, ingestion_run.id, target_tokens=1_000)
        mapping_count = await session.scalar(
            select(func.count()).select_from(RetrievalPassageChunkSpanORM)
        )
        assert mapping_count is not None and mapping_count > 0

        details = await service.details(novel.id)
        assert details is not None
        assert details.retrieval_index_build_id == build.id
        assert details.retrieval_index_status == "degraded_lexical_only"
        assert details.retrieval_passage_count > 0

        ensured = await service.ensure_retrieval_index(novel.id)
        assert ensured is not None
        ensured_build, ensured_run = ensured
        assert ensured_build.id == build.id
        assert ensured_run.id == indexing_run.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_vector_index_resumes_batches_and_hybrid_retrieval_expands_neighbors(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "hybrid.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    content = (
        "第一章 初见\n"
        + "风吹过长廊，竹影摇曳。" * 12
        + "萧炎站在门边，身上的白衣随风轻动。" * 12
        + "远处的人群渐渐散去。" * 12
    ).encode()
    provider = RecoveringEmbeddingProvider()

    async with sessions() as session:
        service = IngestionService(session, artifact_store)
        await service.upload(filename="混合检索.txt", data=content)
        build = await session.scalar(select(RetrievalIndexBuildORM))
        assert build is not None and build.pipeline_run_id is not None
        build.embedding_profile_version = provider.profile.profile_version
        await session.commit()
        collection = qdrant_collection_name(
            embedding_profile_version=provider.profile.profile_version,
            dimension=provider.profile.dimension,
            index_version=build.index_version,
        )
        vector_store = QdrantLocalVectorStore(
            path=tmp_path / "qdrant",
            collection_name=collection,
            dimension=provider.profile.dimension,
        )

        with pytest.raises(RuntimeError, match="temporary_embedding_failure"):
            await process_retrieval_indexing_run(
                session,
                artifact_store,
                build.pipeline_run_id,
                target_tokens=64,
                overlap_tokens=8,
                embedding_provider=provider,
                vector_store=vector_store,
                embedding_batch_size=2,
                lease_seconds=30,
            )
        completed_after_failure = await session.scalar(
            select(func.count())
            .select_from(RetrievalPassageEmbeddingORM)
            .where(RetrievalPassageEmbeddingORM.status == "ready")
        )
        assert completed_after_failure == 2
        first_batch = provider.document_calls[0]

        await process_retrieval_indexing_run(
            session,
            artifact_store,
            build.pipeline_run_id,
            target_tokens=64,
            overlap_tokens=8,
            embedding_provider=provider,
            vector_store=vector_store,
            embedding_batch_size=2,
            lease_seconds=30,
        )
        await session.refresh(build)
        assert build.status == "ready"
        assert first_batch not in provider.document_calls[2:]
        passage_count = await session.scalar(select(func.count()).select_from(RetrievalPassageORM))
        embedding_count = await session.scalar(
            select(func.count()).select_from(RetrievalPassageEmbeddingORM)
        )
        assert passage_count == embedding_count

        result = await HybridRetrievalService(session, provider, vector_store).retrieve(
            build_id=build.id,
            query_text="描写萧炎服装的段落",
            entity_terms=["萧炎"],
            bm25_top_k=4,
            vector_top_k=4,
            rrf_k=60,
            main_hit_limit=1,
            neighbor_count=1,
        )
        assert result.hits[0].vector_rank is not None
        assert any(hit.expansion_reason is not None for hit in result.hits[1:])
        assert [passage.ordinal for passage in result.packet_passages] == sorted(
            passage.ordinal for passage in result.packet_passages
        )
        await vector_store.close()

    await engine.dispose()
