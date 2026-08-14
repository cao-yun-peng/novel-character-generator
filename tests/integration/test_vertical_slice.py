from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from novel_character_generator.application.services import NovelService
from novel_character_generator.infrastructure.db.orm import GeneratedImageORM, PipelineRunORM
from novel_character_generator.infrastructure.db.session import create_engine, create_session_factory
from novel_character_generator.infrastructure.providers.mock import MockImageProvider
from novel_character_generator.infrastructure.storage import LocalArtifactStore
from novel_character_generator.settings import Settings
from novel_character_generator.workers.worker import Worker


async def test_vertical_slice_extracts_character_and_generates_image(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}",
        artifact_root=tmp_path / "artifacts",
    )
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with engine.begin() as connection:
        from novel_character_generator.infrastructure.db.orm import Base

        await connection.run_sync(Base.metadata.create_all)
    service = NovelService()
    provider = MockImageProvider()
    worker = Worker(factory, settings, provider, LocalArtifactStore(settings.artifact_root), "test")

    async with factory() as session:
        novel = await service.import_novel(session, "示例", "第一章\n角色：林昭|黑发，佩剑")
        extraction = await service.submit_extraction(session, novel.id, "extract-once")

    assert await worker.run_once()
    async with factory() as session:
        completed = await session.get(PipelineRunORM, extraction.id)
        characters = await service.list_characters(session, novel.id)
        assert completed is not None and completed.status == "succeeded"
        assert len(characters) == 1
        character = characters[0]
        image_run = await service.submit_image(
            session, novel.id, character.id, "image-once"
        )

    assert await worker.run_once()
    async with factory() as session:
        completed_image = await session.get(PipelineRunORM, image_run.id)
        image = await session.scalar(select(GeneratedImageORM))
        assert completed_image is not None and completed_image.status == "succeeded"
        assert image is not None
        assert Path(image.artifact_uri.removeprefix("file://")).exists()

    await engine.dispose()
