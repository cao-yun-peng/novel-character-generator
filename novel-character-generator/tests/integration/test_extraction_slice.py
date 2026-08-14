from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
