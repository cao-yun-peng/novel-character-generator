from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


@pytest.mark.asyncio
async def test_upload_run_worker_and_query(tmp_path: Path) -> None:
    database_path = tmp_path / "slice.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    content = (
        "第一章 初见\r\n" + "青山依旧。" * 400 + "\r\n第二章 重逢\r\n" + "明月如初。" * 350
    ).encode()

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="故事.txt", data=content)
        duplicate = await service.upload(filename="另一个名字.txt", data=content)
        assert duplicate.id == novel.id
        run = await service.create_run(novel.id, "ingestion-key")
        same_run = await service.create_run(novel.id, "ingestion-key")
        assert run is not None and same_run is not None
        assert same_run.id == run.id
        await process_ingestion_run(session, store, run.id, target_tokens=1_000)
        details = await service.details(novel.id)

    assert details is not None
    assert details.status == "chunked"
    assert details.chapter_count == 2
    assert details.chunk_count >= 2
    async with sessions() as session:
        await process_ingestion_run(session, store, run.id, target_tokens=1_000)
        repeated = await IngestionService(session, store).details(novel.id)
    assert repeated is not None
    assert repeated.chunk_count == details.chunk_count
    await engine.dispose()
