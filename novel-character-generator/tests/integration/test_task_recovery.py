from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.extraction import ChunkExtractionResult
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    PipelineRunORM,
    PipelineStepORM,
    TextChunkORM,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run
from novel_character_generator.workers.task_claim import claim_next_step


class FailOnSecondChunk:
    version = "failure-test-v1"

    def __init__(self) -> None:
        self.calls = 0

    async def extract_chunk(self, _: str) -> ChunkExtractionResult:
        self.calls += 1
        if self.calls == 2:
            raise TimeoutError("provider timeout")
        return ChunkExtractionResult()


class RecordingProvider:
    version = "failure-test-v1"

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def extract_chunk(self, text: str) -> ChunkExtractionResult:
        self.inputs.append(text)
        return ChunkExtractionResult()


@pytest.mark.asyncio
async def test_claim_failure_and_cursor_resume(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    text = "第一章\n" + "青山依旧。" * 400 + "\n第二章\n" + "明月如初。" * 400

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="recovery.txt", data=text.encode())
        ingestion = await service.create_run(novel.id, "recovery-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "recovery-extract")
        assert extraction is not None

    async with sessions() as session:
        claimed = await claim_next_step(session, worker_id="test-worker", lease_seconds=30)
        assert claimed is not None
        assert claimed.run_id == extraction.id
        assert claimed.status == "claimed"

    failing = FailOnSecondChunk()
    async with sessions() as session:
        with pytest.raises(TimeoutError):
            await process_extraction_run(session, failing, extraction.id)
        step = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == extraction.id,
                PipelineStepORM.step_key == "extract_characters",
            )
        )
        run = await session.get(PipelineRunORM, extraction.id)
        assert step is not None and run is not None
        assert step.status == "retry_scheduled"
        assert step.cursor is not None and step.cursor["current_chunk_ordinal"] == 1
        assert run.status == "queued"

    recorder = RecordingProvider()
    async with sessions() as session:
        chunks = list(
            await session.scalars(
                select(TextChunkORM)
                .where(TextChunkORM.novel_id == novel.id)
                .order_by(TextChunkORM.ordinal)
            )
        )
        await process_extraction_run(session, recorder, extraction.id)
        assert recorder.inputs == [chunk.content for chunk in chunks[1:]]
        step = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == extraction.id,
                PipelineStepORM.step_key == "extract_characters",
            )
        )
        assert step is not None and step.status == "succeeded"
        assert step.lease_owner is None
        aggregate_step = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == extraction.id,
                PipelineStepORM.step_key == "aggregate_appearance",
            )
        )
        assert aggregate_step is not None and aggregate_step.status == "queued"

    await engine.dispose()
