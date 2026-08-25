from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.embedding import EmbeddingPort
from novel_character_generator.application.ports.vector_store import VectorStorePort
from novel_character_generator.domain.entities.retrieval import (
    FusedRetrievalHit,
    RankedPassage,
    RetrievalHit,
)
from novel_character_generator.domain.policies.retrieval import (
    ChineseSearchTermBuilder,
    reciprocal_rank_fusion,
)
from novel_character_generator.infrastructure.db.orm import RetrievalPassageORM
from novel_character_generator.infrastructure.db.repositories.retrieval import RetrievalRepository


@dataclass(frozen=True)
class HybridRetrievalResult:
    hits: list[RetrievalHit]
    packet_passages: list[RetrievalPassageORM]


class HybridRetrievalService:
    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: EmbeddingPort,
        vector_store: VectorStorePort,
    ) -> None:
        self.repository = RetrievalRepository(session)
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

    async def retrieve(
        self,
        *,
        build_id: UUID,
        query_text: str,
        entity_terms: list[str],
        bm25_top_k: int = 40,
        vector_top_k: int = 40,
        rrf_k: int = 60,
        main_hit_limit: int = 16,
        neighbor_count: int = 1,
    ) -> HybridRetrievalResult:
        if not query_text.strip():
            raise ValueError("retrieval_query_empty")
        if neighbor_count < 1:
            raise ValueError("retrieval_neighbor_count_must_be_positive")
        build = await self.repository.get_build(build_id)
        if build is None:
            raise ValueError("retrieval_index_not_found")
        if build.status != "ready":
            raise ValueError("retrieval_index_not_ready")
        profile = self.embedding_provider.profile
        if build.embedding_profile_version != profile.profile_version:
            raise ValueError("retrieval_embedding_profile_mismatch")
        if self.vector_store.dimension != profile.dimension:
            raise ValueError("retrieval_vector_dimension_mismatch")
        storage_profile = await self.repository.embedding_storage_profile(
            build_id=build.id,
            embedding_profile_version=profile.profile_version,
        )
        if storage_profile is None:
            raise ValueError("retrieval_vector_index_not_ready")
        stored_dimension, stored_collection = storage_profile
        if stored_dimension != profile.dimension:
            raise ValueError("retrieval_stored_vector_dimension_mismatch")
        if stored_collection != self.vector_store.collection_name:
            raise ValueError("retrieval_vector_collection_mismatch")

        term_builder = ChineseSearchTermBuilder(entity_terms=entity_terms)
        lexical_rows = await self.repository.search_bm25(
            build_id=build.id,
            fts_query=term_builder.query(query_text),
            limit=bm25_top_k,
        )
        query_batch = await self.embedding_provider.embed_queries([query_text])
        if len(query_batch.vectors) != 1:
            raise RuntimeError("retrieval_query_embedding_missing")
        vector_rows = await self.vector_store.search(
            query_batch.vectors[0],
            retrieval_index_build_id=build.id,
            source_document_version_id=build.source_document_version_id,
            limit=vector_top_k,
        )

        passage_ids = list(
            dict.fromkeys(
                [passage.id for passage, _ in lexical_rows]
                + [hit.passage_id for hit in vector_rows]
            )
        )
        passages = await self.repository.get_passages(passage_ids)
        fused = reciprocal_rank_fusion(
            [RankedPassage(passage_id=passage.id, score=score) for passage, score in lexical_rows],
            [RankedPassage(passage_id=hit.passage_id, score=hit.score) for hit in vector_rows],
            passage_contents={
                passage_id: passage.content for passage_id, passage in passages.items()
            },
            entity_terms=entity_terms,
            rrf_k=rrf_k,
        )
        main = fused[:main_hit_limit]
        all_fused = {hit.passage_id: hit for hit in fused}
        selected_ids = {hit.passage_id for hit in main}
        expanded: list[tuple[FusedRetrievalHit | None, UUID, str | None]] = [
            (hit, hit.passage_id, None) for hit in main
        ]

        for main_hit in main:
            main_passage = passages.get(main_hit.passage_id)
            if main_passage is None:
                continue
            frontier = [main_passage]
            for _ in range(neighbor_count):
                neighbor_ids = list(
                    dict.fromkeys(
                        neighbor_id
                        for passage in frontier
                        for neighbor_id in (
                            passage.previous_passage_id,
                            passage.next_passage_id,
                        )
                        if neighbor_id is not None and neighbor_id not in selected_ids
                    )
                )
                neighbor_rows = await self.repository.get_passages(neighbor_ids)
                frontier = []
                for neighbor_id in neighbor_ids:
                    neighbor = neighbor_rows.get(neighbor_id)
                    if (
                        neighbor is None
                        or neighbor.chapter_ordinal != main_passage.chapter_ordinal
                        or neighbor_id in selected_ids
                    ):
                        continue
                    passages[neighbor_id] = neighbor
                    selected_ids.add(neighbor_id)
                    expanded.append(
                        (
                            all_fused.get(neighbor_id),
                            neighbor_id,
                            f"neighbor_of:{main_hit.passage_id}",
                        )
                    )
                    frontier.append(neighbor)

        hits: list[RetrievalHit] = []
        for final_rank, (fused_hit, passage_id, reason) in enumerate(expanded, start=1):
            hits.append(
                RetrievalHit(
                    passage_id=passage_id,
                    source_channels=(fused_hit.source_channels if fused_hit else ("neighbor",)),
                    bm25_score=fused_hit.bm25_score if fused_hit else None,
                    vector_score=fused_hit.vector_score if fused_hit else None,
                    bm25_rank=fused_hit.bm25_rank if fused_hit else None,
                    vector_rank=fused_hit.vector_rank if fused_hit else None,
                    rrf_score=fused_hit.rrf_score if fused_hit else 0.0,
                    exact_entity_match=fused_hit.exact_entity_match if fused_hit else False,
                    expansion_reason=reason,
                    final_rank=final_rank,
                    selected=True,
                )
            )
        packet = sorted(
            (passages[hit.passage_id] for hit in hits if hit.passage_id in passages),
            key=lambda passage: passage.ordinal,
        )
        return HybridRetrievalResult(hits=hits, packet_passages=packet)
