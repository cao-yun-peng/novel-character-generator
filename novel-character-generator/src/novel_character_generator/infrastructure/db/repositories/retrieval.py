from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.domain.entities.retrieval import (
    RetrievalHit,
    RetrievalPassage,
    SearchTerms,
)
from novel_character_generator.infrastructure.db.orm import (
    ChapterORM,
    PipelineRunORM,
    PipelineStepORM,
    RetrievalIndexBuildORM,
    RetrievalPassageChunkSpanORM,
    RetrievalPassageEmbeddingORM,
    RetrievalPassageORM,
    RetrievalQueryHitORM,
    SourceDocumentORM,
    SourceDocumentVersionORM,
    TextChunkORM,
)
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event


class RetrievalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_indexing_run(
        self,
        *,
        novel_id: UUID,
        source_document_version_id: UUID,
        index_version: str,
        config_hash: str,
        passage_algorithm_version: str,
        lexical_profile_version: str,
        embedding_profile_version: str | None,
    ) -> tuple[RetrievalIndexBuildORM, PipelineRunORM]:
        existing = await self.session.scalar(
            select(RetrievalIndexBuildORM).where(
                RetrievalIndexBuildORM.source_document_version_id
                == source_document_version_id,
                RetrievalIndexBuildORM.index_version == index_version,
            )
        )
        if existing is not None:
            if existing.config_hash != config_hash:
                raise RuntimeError("retrieval_index_version_config_conflict")
            if existing.pipeline_run_id is None:
                raise RuntimeError("retrieval_index_build_without_run")
            run = await self.session.get(PipelineRunORM, existing.pipeline_run_id)
            if run is None:
                raise RuntimeError("retrieval_index_run_not_found")
            return existing, run

        now = datetime.now(UTC)
        run = PipelineRunORM(
            id=uuid4(),
            novel_id=novel_id,
            run_type="source_indexing",
            status="queued",
            idempotency_key=f"retrieval-index:{source_document_version_id}:{index_version}",
            cancel_requested=False,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        build = RetrievalIndexBuildORM(
            id=uuid4(),
            source_document_version_id=source_document_version_id,
            index_version=index_version,
            status="queued",
            pipeline_run_id=run.id,
            config_hash=config_hash,
            passage_algorithm_version=passage_algorithm_version,
            lexical_profile_version=lexical_profile_version,
            embedding_profile_version=embedding_profile_version,
            error_summary=None,
            created_at=now,
            updated_at=now,
        )
        step = PipelineStepORM(
            id=uuid4(),
            run_id=run.id,
            step_key="build_retrieval_index",
            status="queued",
            attempt=0,
            lease_owner=None,
            lease_expires_at=None,
            lease_generation=0,
            heartbeat_at=None,
            next_attempt_at=None,
            cursor={"schema_version": "v1", "retrieval_index_build_id": str(build.id)},
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add_all([run, build, step])
        await self.session.flush()
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="run.created",
            payload={
                "run_type": run.run_type,
                "step_key": step.step_key,
                "source_document_version_id": str(source_document_version_id),
                "retrieval_index_build_id": str(build.id),
            },
        )
        return build, run

    async def get_build_for_run(self, run_id: UUID) -> RetrievalIndexBuildORM | None:
        return cast(
            RetrievalIndexBuildORM | None,
            await self.session.scalar(
                select(RetrievalIndexBuildORM).where(
                    RetrievalIndexBuildORM.pipeline_run_id == run_id
                )
            ),
        )

    async def get_build(self, build_id: UUID) -> RetrievalIndexBuildORM | None:
        return await self.session.get(RetrievalIndexBuildORM, build_id)

    async def latest_build_for_source(
        self, source_document_version_id: UUID
    ) -> RetrievalIndexBuildORM | None:
        return cast(
            RetrievalIndexBuildORM | None,
            await self.session.scalar(
                select(RetrievalIndexBuildORM)
                .where(
                    RetrievalIndexBuildORM.source_document_version_id
                    == source_document_version_id
                )
                .order_by(RetrievalIndexBuildORM.created_at.desc())
            ),
        )

    async def get_source(
        self, source_document_version_id: UUID
    ) -> tuple[SourceDocumentORM, SourceDocumentVersionORM] | None:
        row = (
            await self.session.execute(
                select(SourceDocumentORM, SourceDocumentVersionORM)
                .join(
                    SourceDocumentVersionORM,
                    SourceDocumentVersionORM.source_document_id == SourceDocumentORM.id,
                )
                .where(SourceDocumentVersionORM.id == source_document_version_id)
            )
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None

    async def persist_passages(
        self,
        *,
        build: RetrievalIndexBuildORM,
        passages: list[RetrievalPassage],
        search_terms: dict[UUID, SearchTerms],
    ) -> None:
        existing = list(
            await self.session.scalars(
                select(RetrievalPassageORM)
                .where(RetrievalPassageORM.retrieval_index_build_id == build.id)
                .order_by(RetrievalPassageORM.ordinal)
            )
        )
        if existing:
            stored = [(item.id, item.ordinal, item.content_hash) for item in existing]
            incoming = [(item.id, item.ordinal, item.content_hash) for item in passages]
            if stored != incoming:
                raise RuntimeError("immutable_retrieval_index_conflict")
            return

        now = datetime.now(UTC)
        chapter_ids = {
            chapter.ordinal: chapter.id
            for chapter in await self.session.scalars(
                select(ChapterORM).where(
                    ChapterORM.source_document_version_id == build.source_document_version_id
                )
            )
        }
        rows: list[RetrievalPassageORM] = []
        for passage in passages:
            row = RetrievalPassageORM(
                id=passage.id,
                retrieval_index_build_id=build.id,
                chapter_id=chapter_ids.get(passage.chapter_ordinal),
                chapter_ordinal=passage.chapter_ordinal,
                ordinal=passage.ordinal,
                normalized_char_start=passage.normalized_start,
                normalized_char_end=passage.normalized_end,
                original_char_start=passage.original_start,
                original_char_end=passage.original_end,
                content=passage.content,
                token_count=passage.token_count,
                content_hash=passage.content_hash,
                previous_passage_id=passage.previous_passage_id,
                next_passage_id=None,
                oversized_sentence=passage.oversized_sentence,
                created_at=now,
                updated_at=now,
            )
            rows.append(row)
            self.session.add(row)
        await self.session.flush()
        for row, passage in zip(rows, passages, strict=True):
            row.next_passage_id = passage.next_passage_id
        await self.session.flush()

        fts_rows = []
        for passage in passages:
            terms = search_terms[passage.id]
            fts_rows.append(
                {
                    "build_id": str(build.id),
                    "passage_id": str(passage.id),
                    "body_terms": terms.body_terms,
                    "entity_terms": terms.entity_terms,
                    "visual_terms": terms.visual_terms,
                }
            )
        if fts_rows:
            await self.session.execute(
                text(
                    "INSERT INTO retrieval_passages_fts "
                    "(build_id, passage_id, body_terms, entity_terms, visual_terms) "
                    "VALUES (:build_id, :passage_id, :body_terms, :entity_terms, :visual_terms)"
                ),
                fts_rows,
            )
        await self.map_passages_to_chunks(build.source_document_version_id)

    async def map_passages_to_chunks(self, source_document_version_id: UUID) -> int:
        builds = list(
            await self.session.scalars(
                select(RetrievalIndexBuildORM).where(
                    RetrievalIndexBuildORM.source_document_version_id
                    == source_document_version_id
                )
            )
        )
        if not builds:
            return 0
        build_ids = [build.id for build in builds]
        passages = list(
            await self.session.scalars(
                select(RetrievalPassageORM).where(
                    RetrievalPassageORM.retrieval_index_build_id.in_(build_ids)
                )
            )
        )
        chunks = list(
            await self.session.scalars(
                select(TextChunkORM).where(
                    TextChunkORM.source_document_version_id == source_document_version_id
                )
            )
        )
        chapters = {
            chapter.ordinal: chapter.id
            for chapter in await self.session.scalars(
                select(ChapterORM).where(
                    ChapterORM.source_document_version_id == source_document_version_id
                )
            )
        }
        passage_ids = [passage.id for passage in passages]
        if passage_ids:
            await self.session.execute(
                delete(RetrievalPassageChunkSpanORM).where(
                    RetrievalPassageChunkSpanORM.retrieval_passage_id.in_(passage_ids)
                )
            )
        count = 0
        for passage in passages:
            passage.chapter_id = chapters.get(passage.chapter_ordinal)
            for chunk in chunks:
                start = max(passage.normalized_char_start, chunk.normalized_char_start)
                end = min(passage.normalized_char_end, chunk.normalized_char_end)
                if end <= start:
                    continue
                self.session.add(
                    RetrievalPassageChunkSpanORM(
                        id=uuid4(),
                        retrieval_passage_id=passage.id,
                        source_chunk_id=chunk.id,
                        passage_char_start=start - passage.normalized_char_start,
                        passage_char_end=end - passage.normalized_char_start,
                        chunk_char_start=start - chunk.normalized_char_start,
                        chunk_char_end=end - chunk.normalized_char_start,
                    )
                )
                count += 1
        await self.session.flush()
        return count

    async def mark_build(
        self, build: RetrievalIndexBuildORM, *, status: str, error_summary: str | None = None
    ) -> None:
        build.status = status
        build.error_summary = error_summary
        build.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def count_passages(self, build_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(RetrievalPassageORM)
                .where(RetrievalPassageORM.retrieval_index_build_id == build_id)
            )
            or 0
        )

    async def list_passages(self, build_id: UUID) -> list[RetrievalPassageORM]:
        return list(
            await self.session.scalars(
                select(RetrievalPassageORM)
                .where(RetrievalPassageORM.retrieval_index_build_id == build_id)
                .order_by(RetrievalPassageORM.ordinal)
            )
        )

    async def get_passages(self, passage_ids: list[UUID]) -> dict[UUID, RetrievalPassageORM]:
        if not passage_ids:
            return {}
        rows = await self.session.scalars(
            select(RetrievalPassageORM).where(RetrievalPassageORM.id.in_(passage_ids))
        )
        return {row.id: row for row in rows}

    async def completed_embedding_ids(
        self, *, build_id: UUID, embedding_profile_version: str
    ) -> set[UUID]:
        rows = await self.session.execute(
            select(RetrievalPassageEmbeddingORM.retrieval_passage_id)
            .join(
                RetrievalPassageORM,
                RetrievalPassageORM.id
                == RetrievalPassageEmbeddingORM.retrieval_passage_id,
            )
            .where(
                RetrievalPassageORM.retrieval_index_build_id == build_id,
                RetrievalPassageEmbeddingORM.embedding_profile_version
                == embedding_profile_version,
                RetrievalPassageEmbeddingORM.status == "ready",
                RetrievalPassageEmbeddingORM.content_hash == RetrievalPassageORM.content_hash,
            )
        )
        return set(rows.scalars())

    async def embedding_storage_profile(
        self, *, build_id: UUID, embedding_profile_version: str
    ) -> tuple[int, str] | None:
        rows = list(
            await self.session.execute(
                select(
                    RetrievalPassageEmbeddingORM.dimension,
                    RetrievalPassageEmbeddingORM.qdrant_collection,
                )
                .join(
                    RetrievalPassageORM,
                    RetrievalPassageORM.id
                    == RetrievalPassageEmbeddingORM.retrieval_passage_id,
                )
                .where(
                    RetrievalPassageORM.retrieval_index_build_id == build_id,
                    RetrievalPassageEmbeddingORM.embedding_profile_version
                    == embedding_profile_version,
                    RetrievalPassageEmbeddingORM.status == "ready",
                )
                .distinct()
            )
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError("embedding_storage_profile_inconsistent")
        return int(rows[0][0]), str(rows[0][1])

    async def record_ready_embeddings(
        self,
        *,
        passages: list[RetrievalPassageORM],
        embedding_profile_version: str,
        dimension: int,
        qdrant_collection: str,
    ) -> None:
        now = datetime.now(UTC)
        for passage in passages:
            existing = await self.session.scalar(
                select(RetrievalPassageEmbeddingORM).where(
                    RetrievalPassageEmbeddingORM.retrieval_passage_id == passage.id,
                    RetrievalPassageEmbeddingORM.embedding_profile_version
                    == embedding_profile_version,
                )
            )
            if existing is None:
                self.session.add(
                    RetrievalPassageEmbeddingORM(
                        id=uuid4(),
                        retrieval_passage_id=passage.id,
                        embedding_profile_version=embedding_profile_version,
                        dimension=dimension,
                        qdrant_collection=qdrant_collection,
                        qdrant_point_id=str(passage.id),
                        content_hash=passage.content_hash,
                        status="ready",
                        created_at=now,
                        updated_at=now,
                    )
                )
                continue
            if existing.dimension != dimension or existing.qdrant_collection != qdrant_collection:
                raise RuntimeError("embedding_profile_storage_conflict")
            existing.qdrant_point_id = str(passage.id)
            existing.content_hash = passage.content_hash
            existing.status = "ready"
            existing.updated_at = now
        await self.session.flush()

    async def search_bm25(
        self, *, build_id: UUID, fts_query: str, limit: int = 40
    ) -> list[tuple[RetrievalPassageORM, float]]:
        if not fts_query.strip():
            return []
        result = await self.session.execute(
            text(
                "SELECT passage_id, "
                "bm25(retrieval_passages_fts, 0.0, 0.0, 1.0, 2.0, 1.5) AS score "
                "FROM retrieval_passages_fts "
                "WHERE retrieval_passages_fts MATCH :query AND build_id = :build_id "
                "ORDER BY score LIMIT :limit"
            ),
            {"query": fts_query, "build_id": str(build_id), "limit": limit},
        )
        hits: list[tuple[RetrievalPassageORM, float]] = []
        for passage_id, score in result:
            passage = await self.session.get(RetrievalPassageORM, UUID(passage_id))
            if passage is not None and passage.retrieval_index_build_id == build_id:
                hits.append((passage, float(score)))
        return hits

    async def record_query_hits(
        self, *, retrieval_query_run_id: UUID, hits: list[RetrievalHit]
    ) -> None:
        existing = list(
            await self.session.scalars(
                select(RetrievalQueryHitORM)
                .where(
                    RetrievalQueryHitORM.retrieval_query_run_id
                    == retrieval_query_run_id
                )
                .order_by(RetrievalQueryHitORM.final_rank)
            )
        )
        incoming_signature = [
            (
                hit.passage_id,
                hit.source_channels,
                hit.bm25_rank,
                hit.vector_rank,
                hit.final_rank,
                hit.expansion_reason,
            )
            for hit in hits
        ]
        if existing:
            stored_signature = [
                (
                    hit.retrieval_passage_id,
                    tuple(hit.source_channels),
                    hit.bm25_rank,
                    hit.vector_rank,
                    hit.final_rank,
                    hit.expansion_reason,
                )
                for hit in existing
            ]
            if stored_signature != incoming_signature:
                raise RuntimeError("immutable_retrieval_query_hits_conflict")
            return
        now = datetime.now(UTC)
        self.session.add_all(
            [
                RetrievalQueryHitORM(
                    id=uuid4(),
                    retrieval_query_run_id=retrieval_query_run_id,
                    retrieval_passage_id=hit.passage_id,
                    source_channels=list(hit.source_channels),
                    bm25_score=hit.bm25_score,
                    vector_score=hit.vector_score,
                    bm25_rank=hit.bm25_rank,
                    vector_rank=hit.vector_rank,
                    rrf_score=hit.rrf_score,
                    expansion_reason=hit.expansion_reason,
                    final_rank=hit.final_rank,
                    selected=hit.selected,
                    created_at=now,
                    updated_at=now,
                )
                for hit in hits
            ]
        )
        await self.session.flush()
