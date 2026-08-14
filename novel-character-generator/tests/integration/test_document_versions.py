from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    NormalizationMapORM,
    SourceDocumentORM,
    SourceDocumentVersionORM,
    TextChunkORM,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


@pytest.mark.asyncio
async def test_new_upload_creates_immutable_source_version(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'versions.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    first_text = "第一章 初见\n" + "青山依旧。" * 300
    second_text = first_text + "\n第二章 重逢\n" + "明月如初。" * 250

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="story.txt", data=first_text.encode())
        first_run = await service.create_run(novel.id, "version-1-ingest")
        assert first_run is not None
        await process_ingestion_run(session, store, first_run.id, target_tokens=1_000)
        document = await service.repository.latest_document(novel.id)
        first_version = await service.repository.latest_document_version(novel.id)
        assert document is not None and first_version is not None
        first_chunk_ids = set(
            await session.scalars(
                select(TextChunkORM.id).where(
                    TextChunkORM.source_document_version_id == first_version.id
                )
            )
        )

        second_version = await service.upload_version(
            novel_id=novel.id,
            filename="story.txt",
            data=second_text.encode(),
        )
        assert second_version is not None
        assert second_version.version == 2
        assert second_version.supersedes_version_id == first_version.id
        assert document.current_version_id == second_version.id
        second_run = await service.create_run(novel.id, "version-2-ingest")
        assert second_run is not None
        await process_ingestion_run(session, store, second_run.id, target_tokens=1_000)

        versions = list(
            await session.scalars(
                select(SourceDocumentVersionORM)
                .where(SourceDocumentVersionORM.source_document_id == document.id)
                .order_by(SourceDocumentVersionORM.version)
            )
        )
        assert [item.version for item in versions] == [1, 2]
        assert all(item.normalization_map_id is not None for item in versions)
        assert await session.scalar(select(func.count()).select_from(NormalizationMapORM)) == 2
        assert first_chunk_ids == set(
            await session.scalars(
                select(TextChunkORM.id).where(
                    TextChunkORM.source_document_version_id == first_version.id
                )
            )
        )
        assert await session.get(SourceDocumentORM, document.id) is not None

    await engine.dispose()
