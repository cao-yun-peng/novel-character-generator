from asyncio import to_thread
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.extraction import (
    DetailedExtractionResult,
    ExtractionCallMetadata,
    ExtractionTokenUsage,
    VisualCandidateExtractionResult,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.application.services.run_service import RunService
from novel_character_generator.infrastructure.db.orm import (
    PipelineRunORM,
    PipelineStepORM,
    RunEventORM,
    TextChunkORM,
)
from novel_character_generator.infrastructure.llm.openai_compatible import (
    ProviderExtractionError,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run
from novel_character_generator.workers.task_claim import claim_next_step


class FailOnSecondChunk:
    version = "failure-test-v1"

    def __init__(self) -> None:
        self.calls = 0

    async def extract_chunk(self, _: str) -> VisualCandidateExtractionResult:
        self.calls += 1
        if self.calls == 2:
            raise ProviderExtractionError(
                "provider_total_deadline_exceeded",
                retryable=True,
                attempts=2,
            )
        return VisualCandidateExtractionResult()


class RecordingProvider:
    version = "failure-test-v1"

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        self.inputs.append(text)
        return VisualCandidateExtractionResult()

    async def extract_chunk_detailed(self, text: str) -> DetailedExtractionResult:
        self.inputs.append(text)
        return DetailedExtractionResult(
            output=VisualCandidateExtractionResult(),
            metadata=ExtractionCallMetadata(
                wire_api="responses",
                provider_request_id="request-test",
                response_model="model-test",
                status="completed",
                finish_reason=None,
                latency_ms=12,
                usage=ExtractionTokenUsage(input_tokens=10, output_tokens=2, total_tokens=12),
            ),
        )


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
        with pytest.raises(ProviderExtractionError):
            await process_extraction_run(session, failing, extraction.id)
        step = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == extraction.id,
                PipelineStepORM.step_key == "extract_characters",
            )
        )
        run = await session.get(PipelineRunORM, extraction.id)
        assert step is not None and run is not None
        assert step.status == "failed"
        assert step.cursor is not None and step.cursor["current_chunk_ordinal"] == 1
        assert run.status == "failed"
        deferred_event = await session.scalar(
            select(RunEventORM).where(
                RunEventORM.run_id == extraction.id,
                RunEventORM.event_type == "provider.extraction.deferred",
            )
        )
        assert deferred_event is not None
        assert deferred_event.payload["provider_attempts"] == 2
        retried = await RunService(session).retry(extraction.id, max_attempts=3)
        assert retried is not None and retried.status == "queued"

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
        assert step.cursor is not None and step.cursor["schema_version"] == "v3"
        assert step.cursor["stage"] == "completed"
        assert step.lease_owner is None
        assert step.next_attempt_at is None
        assert step.error_code is None
        assert step.error_message is None
        phase_step = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == extraction.id,
                PipelineStepORM.step_key == "resolve_character_phases",
            )
        )
        assert phase_step is not None and phase_step.status == "queued"
        provider_events = list(
            await session.scalars(
                select(RunEventORM).where(
                    RunEventORM.run_id == extraction.id,
                    RunEventORM.event_type == "provider.extraction.completed",
                )
            )
        )
        assert len(provider_events) == len(chunks[1:])
        assert provider_events[0].payload["wire_api"] == "responses"
        assert provider_events[0].payload["usage"]["total_tokens"] == 12

    await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_marks_expired_running_step_cancelled(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'stale-cancel.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")

    async with sessions() as session:
        ingestion = IngestionService(session, store)
        novel = await ingestion.upload(filename="stale.txt", data="第一章\n测试".encode())
        run = await ingestion.create_run(novel.id, "stale-ingestion")
        assert run is not None
        step = await session.scalar(select(PipelineStepORM).where(PipelineStepORM.run_id == run.id))
        stored_run = await session.get(PipelineRunORM, run.id)
        assert step is not None and stored_run is not None
        stored_run.status = "running"
        step.status = "running"
        step.lease_owner = "dead-worker"
        step.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

        details = await RunService(session).request_cancel(run.id)
        assert details is not None
        assert details.status == "cancelled"
        assert details.cancel_requested is True
        assert details.steps[0].status == "cancelled"
        await session.refresh(step)
        assert step.lease_owner is None
        assert step.lease_expires_at is None
        assert step.lease_generation == 1

    await engine.dispose()
