from asyncio import to_thread
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.embedding import (
    EmbeddingBatch,
    EmbeddingProfile,
)
from novel_character_generator.application.ports.visual_enrichment import (
    VisualEnrichmentResult,
    VisualEvidenceDraft,
    VisualEvidencePacket,
)
from novel_character_generator.application.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.application.services.visual_enrichment_service import (
    VisualEnrichmentService,
)
from novel_character_generator.infrastructure.db.orm import (
    CharacterORM,
    FeatureObservationORM,
    FeatureSuggestionORM,
    PipelineStepORM,
    RetrievalIndexBuildORM,
    RetrievalQueryHitORM,
    RetrievalQueryRunORM,
    VisualEnrichmentRejectionORM,
)
from novel_character_generator.infrastructure.llm.visual_enrichment import (
    MockVisualEnrichmentProvider,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.infrastructure.vector.qdrant_local import (
    QdrantLocalVectorStore,
    qdrant_collection_name,
)
from novel_character_generator.workers.handlers.appearance_aggregation import (
    process_appearance_aggregation_run,
)
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run
from novel_character_generator.workers.handlers.retrieval_indexing import (
    process_retrieval_indexing_run,
)
from novel_character_generator.workers.handlers.visual_enrichment import (
    process_visual_enrichment_run,
)


class VisualTestEmbeddingProvider:
    def __init__(self) -> None:
        self._profile = EmbeddingProfile(
            provider="test",
            model="visual-test",
            model_revision="r1",
            dimension=3,
            profile_version="visual-test-v1",
            normalization="l2",
            document_prefix="passage: ",
            query_prefix="query: ",
        )

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    @staticmethod
    def _vector(text: str) -> list[float]:
        if any(term in text for term in ("白衣", "服装", "衣着", "斗篷")):
            return [1.0, 0.0, 0.0]
        if any(term in text for term in ("黑发", "长发", "头发", "发型")):
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    async def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(vectors=[self._vector(text) for text in texts])

    async def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(vectors=[self._vector(text) for text in texts])

    async def close(self) -> None:
        return None


class OffsetRepairAndRejectionProvider:
    provider = "test"
    model = "offset-repair"
    model_revision = "r1"
    version = "test:offset-repair:visual-enrichment-v1"

    async def extract_visual_evidence(
        self, packet: VisualEvidencePacket
    ) -> VisualEnrichmentResult:
        passage = packet.passages[0]
        quote = passage.content
        return VisualEnrichmentResult(
            observations=[
                VisualEvidenceDraft(
                    character_id=packet.character_id,
                    retrieval_passage_id=passage.passage_id,
                    field_path="face.description",
                    value="有直接面部描述",
                    evidence_quote=quote,
                    start=1,
                    end=len(quote) + 1,
                    evidence_kind="direct",
                    epistemic_status="asserted",
                    confidence=0.9,
                ),
                VisualEvidenceDraft(
                    character_id=packet.character_id,
                    retrieval_passage_id=passage.passage_id,
                    field_path="occupation",
                    value="铁匠",
                    evidence_quote=quote,
                    start=0,
                    end=len(quote),
                    evidence_kind="direct",
                    epistemic_status="asserted",
                    confidence=0.9,
                ),
            ]
        )


class OnlyInvalidVisualProvider:
    provider = "test"
    model = "only-invalid"
    model_revision = "r1"
    version = "test:only-invalid:visual-enrichment-v1"

    async def extract_visual_evidence(
        self, packet: VisualEvidencePacket
    ) -> VisualEnrichmentResult:
        passage = packet.passages[0]
        return VisualEnrichmentResult(
            observations=[
                VisualEvidenceDraft(
                    character_id=packet.character_id,
                    retrieval_passage_id=passage.passage_id,
                    field_path="occupation",
                    value="铁匠",
                    evidence_quote=passage.content,
                    start=0,
                    end=len(passage.content),
                    evidence_kind="direct",
                    epistemic_status="asserted",
                    confidence=0.9,
                )
            ]
        )


@pytest.mark.asyncio
async def test_visual_enrichment_persists_exact_facts_and_auditable_hits(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'visual-enrichment.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    provider = VisualTestEmbeddingProvider()
    content = (
        "第一章 初见\n"
        + "萧炎披着白衣站在门边，乌黑的长发被风吹起。" * 20
        + "长廊外竹影摇曳，众人渐渐散去。" * 30
        + "一个瘦小的身影从雨幕中走来。" * 12
    ).encode()

    async with sessions() as session:
        ingestion = IngestionService(session, store)
        novel = await ingestion.upload(filename="视觉精提取.txt", data=content)
        build = await session.scalar(select(RetrievalIndexBuildORM))
        assert build is not None and build.pipeline_run_id is not None
        build.embedding_profile_version = provider.profile.profile_version
        await session.commit()
        vector_store = QdrantLocalVectorStore(
            path=tmp_path / "qdrant",
            collection_name=qdrant_collection_name(
                embedding_profile_version=provider.profile.profile_version,
                dimension=provider.profile.dimension,
                index_version=build.index_version,
            ),
            dimension=provider.profile.dimension,
        )
        await process_retrieval_indexing_run(
            session,
            store,
            build.pipeline_run_id,
            target_tokens=64,
            overlap_tokens=8,
            embedding_provider=provider,
            vector_store=vector_store,
            embedding_batch_size=4,
            lease_seconds=30,
        )

        analysis_run = await ingestion.create_run(novel.id, "visual-enrichment-chunking")
        assert analysis_run is not None
        await process_ingestion_run(session, store, analysis_run.id, target_tokens=1_000)
        character = CharacterORM(
            id=uuid4(),
            novel_id=novel.id,
            canonical_name="萧炎",
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(character)
        await session.commit()

        visual_service = VisualEnrichmentService(session)
        initial_gaps = await visual_service.field_gap_plan(
            character_id=character.id, life_phase_key="adolescence"
        )
        assert initial_gaps.retrieval_index_status == "ready"
        assert set(initial_gaps.recommended_field_groups) == {
            "hair",
            "face",
            "body",
            "clothing",
            "accessories",
            "marks_injuries",
            "disguise_cleanliness",
        }
        run = await visual_service.create_run(
            character_id=character.id,
            field_groups=[],
            life_phase_key="adolescence",
            max_provider_calls=1,
            context_budget_tokens=4_000,
            idempotency_key="visual-enrichment-test",
            auto_plan=True,
        )
        await process_visual_enrichment_run(session, run.id)
        retrieval = HybridRetrievalService(session, provider, vector_store)
        await process_visual_enrichment_run(session, run.id, retrieval=retrieval)
        await process_visual_enrichment_run(
            session, run.id, provider=MockVisualEnrichmentProvider()
        )
        await process_visual_enrichment_run(session, run.id)
        await process_appearance_aggregation_run(session, run.id, lease_seconds=30)

        await session.refresh(run)
        assert run.status == "succeeded"
        query_run = await session.scalar(
            select(RetrievalQueryRunORM).where(
                RetrievalQueryRunORM.enrichment_run_id == run.id
            )
        )
        assert query_run is not None
        assert query_run.query_plan["version"] == "visual-query-plan-v1"
        hit_count = await session.scalar(
            select(func.count())
            .select_from(RetrievalQueryHitORM)
            .where(RetrievalQueryHitORM.retrieval_query_run_id == query_run.id)
        )
        assert hit_count is not None and hit_count > 0

        observations = list(
            await session.scalars(
                select(FeatureObservationORM).where(
                    FeatureObservationORM.extraction_run_id == run.id
                )
            )
        )
        assert observations
        assert all(item.grounding_status == "exact" for item in observations)
        assert all(item.source_chunk_id is not None for item in observations)
        assert all(item.retrieval_passage_id is not None for item in observations)
        assert {item.temporal_scope.get("life_phase_key") for item in observations} == {
            "adolescence"
        }

        suggestions = list(
            await session.scalars(
                select(FeatureSuggestionORM).where(
                    FeatureSuggestionORM.enrichment_run_id == run.id
                )
            )
        )
        assert suggestions
        assert all(item.status == "candidate" for item in suggestions)
        assert all(item.evidence_links for item in suggestions)
        updated_gaps = await visual_service.field_gap_plan(
            character_id=character.id, life_phase_key="adolescence"
        )
        covered_groups = {item.field_group for item in updated_gaps.groups if item.covered}
        assert {"hair", "clothing"} <= covered_groups

        repair_run = await visual_service.create_run(
            character_id=character.id,
            field_groups=["face"],
            life_phase_key="adolescence",
            max_provider_calls=1,
            context_budget_tokens=4_000,
            idempotency_key="visual-offset-repair-test",
            auto_plan=False,
        )
        await process_visual_enrichment_run(session, repair_run.id)
        await process_visual_enrichment_run(session, repair_run.id, retrieval=retrieval)
        await process_visual_enrichment_run(
            session, repair_run.id, provider=OffsetRepairAndRejectionProvider()
        )
        await process_visual_enrichment_run(session, repair_run.id)
        repaired_observation = await session.scalar(
            select(FeatureObservationORM).where(
                FeatureObservationORM.extraction_run_id == repair_run.id,
                FeatureObservationORM.field_path == "face.description",
            )
        )
        assert repaired_observation is not None
        assert repaired_observation.grounding_status == "exact"
        rejection = await session.scalar(
            select(VisualEnrichmentRejectionORM).where(
                VisualEnrichmentRejectionORM.enrichment_run_id == repair_run.id
            )
        )
        assert rejection is not None
        assert rejection.reason_codes == ["field_not_visual"]
        assert rejection.draft["field_path"] == "occupation"

        invalid_run = await visual_service.create_run(
            character_id=character.id,
            field_groups=["marks_injuries"],
            life_phase_key="adolescence",
            max_provider_calls=1,
            context_budget_tokens=4_000,
            idempotency_key="visual-only-invalid-test",
            auto_plan=False,
        )
        await process_visual_enrichment_run(session, invalid_run.id)
        await process_visual_enrichment_run(session, invalid_run.id, retrieval=retrieval)
        await process_visual_enrichment_run(
            session, invalid_run.id, provider=OnlyInvalidVisualProvider()
        )
        await process_visual_enrichment_run(session, invalid_run.id)
        await session.refresh(invalid_run)
        assert invalid_run.status == "succeeded"
        persist_step = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == invalid_run.id,
                PipelineStepORM.step_key == "persist_visual_evidence",
            )
        )
        assert persist_step is not None
        assert persist_step.cursor is not None
        assert persist_step.cursor["result_status"] == "no_valid_results"
        assert persist_step.cursor["observation_ids"] == []
        assert persist_step.cursor["suggestion_ids"] == []
        assert persist_step.cursor["rejected_count"] == 1
        await vector_store.close()

    await engine.dispose()
