from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.extraction import (
    ChunkExtractionResult,
    MentionDraft,
    ObservationDraft,
    RelationDraft,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    CharacterORM,
    CharacterRelationORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    MentionSpanORM,
)
from novel_character_generator.infrastructure.llm.mock import MockExtractionProvider
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


class LegacyVisualProvider:
    version = "legacy-visual-test-v1"

    async def extract_chunk(self, text: str) -> ChunkExtractionResult:
        appearance_quote = "皮肤呈现出健康的小麦色，黑色短发，一身衣服虽然朴素但很干净"
        appearance_start = text.index(appearance_quote)
        build_quote = "身材瘦小"
        build_start = text.index(build_quote)
        return ChunkExtractionResult(
            observations=[
                ObservationDraft(
                    character_name="唐三",
                    field_path="appearance",
                    value=appearance_quote,
                    evidence_quote=appearance_quote,
                    start=appearance_start + 1,
                    end=appearance_start + len(appearance_quote) + 1,
                    confidence=0.97,
                    life_phase_key="reincarnated_childhood",
                    life_phase_label="转生幼年",
                ),
                ObservationDraft(
                    character_name="唐三",
                    field_path="appearance.build",
                    value="瘦小",
                    evidence_quote=build_quote,
                    start=build_start,
                    end=build_start + len(build_quote),
                    confidence=0.95,
                    life_phase_key="reincarnated_childhood",
                    life_phase_label="转生幼年",
                ),
            ]
        )


class ModernVisualProvider(LegacyVisualProvider):
    version = "modern-visual-test-v2"


class FailingModernVisualProvider(ModernVisualProvider):
    version = "failing-modern-visual-test-v3"

    async def extract_chunk(self, text: str) -> ChunkExtractionResult:
        result = await super().extract_chunk(text)
        if "第二章" in text:
            raise ValueError("provider_failed_on_second_chunk")
        return result


class KinshipRelationProvider:
    version = "kinship-relation-test-v1"

    async def extract_chunk(self, text: str) -> ChunkExtractionResult:
        quote = "唐三的父亲唐昊"
        start = text.index(quote)
        father_start = text.index("父亲", start)
        return ChunkExtractionResult(
            mentions=[
                MentionDraft(
                    text="唐三",
                    canonical_name="唐三",
                    start=start,
                    end=start + 2,
                    kind="name",
                ),
                MentionDraft(
                    text="父亲",
                    canonical_name="唐三的父亲",
                    start=father_start,
                    end=father_start + 2,
                    kind="kinship",
                ),
                MentionDraft(
                    text="唐昊",
                    canonical_name="唐昊",
                    start=start + len(quote) - 2,
                    end=start + len(quote),
                    kind="name",
                ),
            ],
            observations=[
                ObservationDraft(
                    character_name="唐三",
                    field_path="family.father",
                    value="唐昊",
                    evidence_quote=quote,
                    start=start,
                    end=start + len(quote),
                    confidence=1.0,
                )
            ],
            relations=[
                RelationDraft(
                    source_character_name="唐三",
                    target_character_name="唐三的父亲",
                    relation_type="父亲",
                    evidence_quote=quote,
                    start=start,
                    end=start + len(quote),
                    confidence=1.0,
                )
            ],
        )


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
        assert expressions
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
async def test_family_fact_persists_relation_and_resolves_kinship_placeholder(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'kinship-relation.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "kinship-relation-artifacts")

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(
            filename="kinship.txt", data="第一章\n唐三的父亲唐昊是一名铁匠。".encode()
        )
        ingestion = await service.create_run(novel.id, "kinship-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "kinship-extract")
        assert extraction is not None
        await process_extraction_run(session, KinshipRelationProvider(), extraction.id)

        characters = list(
            await session.scalars(
                select(CharacterORM).where(CharacterORM.novel_id == novel.id)
            )
        )
        assert {item.canonical_name for item in characters} == {"唐三", "唐昊"}
        by_name = {item.canonical_name: item for item in characters}
        relation = await session.scalar(select(CharacterRelationORM))
        assert relation is not None
        assert relation.source_character_id == by_name["唐三"].id
        assert relation.target_character_id == by_name["唐昊"].id
        assert relation.relation_type == "father"
        assert relation.record_status == "active"
        kinship_mention = await session.scalar(
            select(MentionSpanORM).where(MentionSpanORM.mention_text == "父亲")
        )
        assert kinship_mention is not None
        assert kinship_mention.resolved_character_id == by_name["唐昊"].id

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
        await process_extraction_run(session, LegacyVisualProvider(), original.id)

        replacement = await service.create_extraction_run(novel.id, "failed-extract")
        assert replacement is not None
        with pytest.raises(ValueError, match="provider_failed_on_second_chunk"):
            await process_extraction_run(
                session,
                FailingModernVisualProvider(),
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
        assert replacement_rows
        assert all(item.record_status == "pending" for item in replacement_rows)

    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_visual_fields_are_normalized_and_phase_scoped(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'visual-normalization.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "visual-artifacts")
    text = (
        "第一章\n唐三皮肤呈现出健康的小麦色，黑色短发，"
        "一身衣服虽然朴素但很干净，而且身材瘦小。"
    )

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="visual.txt", data=text.encode())
        ingestion = await service.create_run(novel.id, "visual-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "visual-extract")
        assert extraction is not None
        await process_extraction_run(session, LegacyVisualProvider(), extraction.id)

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

        replacement = await service.create_extraction_run(novel.id, "visual-extract-v2")
        assert replacement is not None
        await process_extraction_run(session, ModernVisualProvider(), replacement.id)
        all_observations = list(
            await session.scalars(
                select(FeatureObservationORM).order_by(FeatureObservationORM.created_at)
            )
        )
        active = [item for item in all_observations if item.record_status == "active"]
        superseded = [
            item for item in all_observations if item.record_status == "superseded"
        ]
        assert len(active) == 6
        assert len(superseded) == 6
        assert all(item.extraction_run_id == replacement.id for item in active)
        assert all(item.invalidated_by_run_id == replacement.id for item in superseded)

    await engine.dispose()
