from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.extraction import (
    VisualCandidateExtractionResult,
    VisualEntityCandidate,
    VisualFactCandidate,
    VisualTemporalSignal,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    CharacterORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    MentionSpanORM,
)
from novel_character_generator.infrastructure.llm.mock import MockExtractionProvider
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run
from novel_character_generator.workers.handlers.phase_resolution import (
    process_phase_resolution_run,
)


class VisualProvider:
    version = "visual-candidate-test-v3"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        appearance_quote = "皮肤呈现出健康的小麦色，黑色短发，一身衣服虽然朴素但很干净"
        build_quote = "身材瘦小"
        assert appearance_quote in text and build_quote in text
        phase = VisualTemporalSignal(
            kind="life_phase",
            label="转生幼年",
            evidence_quote="唐三",
        )
        facts = [
            ("skin.color", "小麦色", "健康的小麦色"),
            ("hair.color", "黑色", "黑色短发"),
            ("hair.length", "短", "黑色短发"),
            ("clothing.style", "朴素", "一身衣服虽然朴素但很干净"),
            ("cleanliness", "干净", "一身衣服虽然朴素但很干净"),
            ("body.build", "瘦小", build_quote),
        ]
        return VisualCandidateExtractionResult(
            entities=[
                VisualEntityCandidate(
                    local_id="e1",
                    representative_name="唐三",
                    mention_quote="唐三",
                    mention_kind="name",
                    confidence=1.0,
                )
            ],
            visual_candidates=[
                VisualFactCandidate(
                    entity_ref="e1",
                    field_path=field_path,
                    value=value,
                    evidence_quote=quote,
                    confidence=0.97,
                    temporal_signals=[phase],
                )
                for field_path, value, quote in facts
            ],
        )


class FailingVisualProvider(VisualProvider):
    version = "failing-modern-visual-test-v3"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        result = await super().extract_chunk(text)
        if "第二章" in text:
            raise ValueError("provider_failed_on_second_chunk")
        return result


@pytest.mark.asyncio
async def test_character_extraction_slice_is_grounded_and_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "extraction.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    text = (
        "第一章 初见\n少年沈砚披着旧青氅。他左眼下有一颗浅痣，"
        "茶摊老板称他为“阿砚”。沈砚嘴角微扬。\n"
        "顾清遥约莫十七岁，长发乌黑，腰间系着白玉铃，她神色平静。"
    )
    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="characters.txt", data=text.encode())
        ingestion = await service.create_run(novel.id, "ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "extract")
        assert extraction is not None
        await process_extraction_run(session, MockExtractionProvider(), extraction.id)
        characters = list(
            await session.scalars(select(CharacterORM).where(CharacterORM.novel_id == novel.id))
        )
        names = {character.canonical_name for character in characters}
        assert {"沈砚", "顾清遥"} <= names
        observations = list(await session.scalars(select(FeatureObservationORM)))
        assert observations
        assert all(item.grounding_status == "exact" for item in observations)
        assert all(item.evidence_quote is not None for item in observations)
        expressions = list(await session.scalars(select(ExpressionObservationORM)))
        assert expressions == []
        mentions = list(await session.scalars(select(MentionSpanORM)))
        assert any(item.mention_text == "沈砚" for item in mentions)
        counts_before = (
            await session.scalar(select(func.count()).select_from(FeatureObservationORM)),
            await session.scalar(select(func.count()).select_from(ExpressionObservationORM)),
        )
        await process_extraction_run(session, MockExtractionProvider(), extraction.id)
        counts_after = (
            await session.scalar(select(func.count()).select_from(FeatureObservationORM)),
            await session.scalar(select(func.count()).select_from(ExpressionObservationORM)),
        )
        assert counts_after == counts_before
    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_replacement_keeps_old_facts_active_and_new_facts_pending(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'failed-replacement.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "failed-replacement-artifacts")
    text = (
        "第一章\n唐三皮肤呈现出健康的小麦色，黑色短发，"
        "一身衣服虽然朴素但很干净，而且身材瘦小。\n"
        "第二章\n唐三皮肤呈现出健康的小麦色，黑色短发，"
        "一身衣服虽然朴素但很干净，而且身材瘦小。"
    )

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="failed-replacement.txt", data=text.encode())
        ingestion = await service.create_run(novel.id, "failed-replacement-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        original = await service.create_extraction_run(novel.id, "original-extract")
        assert original is not None
        await process_extraction_run(session, VisualProvider(), original.id)
        await process_phase_resolution_run(session, original.id)

        replacement = await service.create_extraction_run(novel.id, "failed-extract")
        assert replacement is not None
        with pytest.raises(ValueError, match="provider_failed_on_second_chunk"):
            await process_extraction_run(
                session,
                FailingVisualProvider(),
                replacement.id,
                max_attempts=1,
            )

        old_rows = list(
            await session.scalars(
                select(FeatureObservationORM).where(
                    FeatureObservationORM.extraction_run_id == original.id
                )
            )
        )
        replacement_rows = list(
            await session.scalars(
                select(FeatureObservationORM).where(
                    FeatureObservationORM.extraction_run_id == replacement.id
                )
            )
        )
        assert old_rows and all(item.record_status == "active" for item in old_rows)
        # R2 fails closed: a run that never reaches its convergence boundary
        # leaves candidates persisted for recovery but publishes no observations.
        assert replacement_rows == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_v3_visual_fields_are_phase_scoped_and_superseded(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'visual-normalization.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "visual-artifacts")
    text = "第一章\n唐三皮肤呈现出健康的小麦色，黑色短发，一身衣服虽然朴素但很干净，而且身材瘦小。"

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="visual.txt", data=text.encode())
        ingestion = await service.create_run(novel.id, "visual-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "visual-extract")
        assert extraction is not None
        await process_extraction_run(session, VisualProvider(), extraction.id)
        await process_phase_resolution_run(session, extraction.id)

        observations = list(
            await session.scalars(
                select(FeatureObservationORM).order_by(FeatureObservationORM.field_path)
            )
        )
        assert {item.field_path for item in observations} == {
            "body.build",
            "cleanliness",
            "clothing.style",
            "hair.color",
            "hair.length",
            "skin.color",
        }
        assert all(item.grounding_status == "exact" for item in observations)
        assert all(
            item.temporal_scope["life_phase_key"] == "reincarnated_childhood"
            and item.temporal_scope["life_phase_label"] == "转生幼年"
            for item in observations
        )

        replacement = await service.create_extraction_run(novel.id, "visual-extract-v3-repeat")
        assert replacement is not None
        replacement_provider = VisualProvider()
        replacement_provider.version = "visual-candidate-test-v3-revision"
        await process_extraction_run(session, replacement_provider, replacement.id)
        await process_phase_resolution_run(session, replacement.id)
        all_observations = list(
            await session.scalars(
                select(FeatureObservationORM).order_by(FeatureObservationORM.created_at)
            )
        )
        active = [item for item in all_observations if item.record_status == "active"]
        superseded = [item for item in all_observations if item.record_status == "superseded"]
        assert len(active) == 6
        assert len(superseded) == 6
        assert all(item.extraction_run_id == replacement.id for item in active)
        assert all(item.invalidated_by_run_id == replacement.id for item in superseded)

    await engine.dispose()
