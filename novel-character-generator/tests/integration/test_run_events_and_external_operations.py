from asyncio import to_thread
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.domain.entities.pipeline import ExternalOperationState
from novel_character_generator.infrastructure.db.orm import PipelineStepORM
from novel_character_generator.infrastructure.db.repositories.external_operations import (
    ExternalOperationConflict,
    ExternalOperationRepository,
)
from novel_character_generator.infrastructure.db.repositories.run_events import (
    append_run_event,
    read_run_events,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore


@pytest.mark.asyncio
async def test_run_events_are_append_only_and_support_resume(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'run-events.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="events.txt", data="第一章".encode())
        run = await service.create_run(novel.id, "events-ingest")
        assert run is not None
        await append_run_event(
            session,
            run_id=run.id,
            event_type="test.progress",
            payload={"progress": 0.5},
        )
        await append_run_event(
            session,
            run_id=run.id,
            event_type="test.completed",
            payload={"progress": 1.0},
        )
        await session.commit()

    async with sessions() as session:
        all_events = await read_run_events(session, run_id=run.id, after_sequence=0)
        resumed_events = await read_run_events(session, run_id=run.id, after_sequence=1)
        assert [event.sequence for event in all_events] == [1, 2, 3]
        assert [event.event_type for event in all_events] == [
            "run.created",
            "test.progress",
            "test.completed",
        ]
        assert [event.sequence for event in resumed_events] == [2, 3]

    await engine.dispose()


@pytest.mark.asyncio
async def test_external_operation_enforces_idempotency_and_fencing(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'external-operations.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="operation.txt", data="第一章".encode())
        run = await service.create_run(novel.id, "operation-ingest")
        assert run is not None
        step = await session.scalar(
            select(PipelineStepORM).where(PipelineStepORM.run_id == run.id)
        )
        assert step is not None
        lease_generation = step.lease_generation
        repository = ExternalOperationRepository(session)
        operation = await repository.prepare(
            run_id=run.id,
            step_id=step.id,
            provider="image-provider",
            operation_kind="generate-image",
            idempotency_key="operation-1",
            request_fingerprint="a" * 64,
            lease_generation=lease_generation,
        )
        same_operation = await repository.prepare(
            run_id=run.id,
            step_id=step.id,
            provider="image-provider",
            operation_kind="generate-image",
            idempotency_key="operation-1",
            request_fingerprint="a" * 64,
            lease_generation=lease_generation,
        )
        assert same_operation.id == operation.id
        with pytest.raises(ExternalOperationConflict, match="idempotency"):
            await repository.prepare(
                run_id=run.id,
                step_id=step.id,
                provider="image-provider",
                operation_kind="generate-image",
                idempotency_key="operation-1",
                request_fingerprint="b" * 64,
                lease_generation=lease_generation,
            )

        submitting = await repository.transition(
            operation.id,
            target=ExternalOperationState.SUBMITTING,
            expected_generation=lease_generation,
        )
        assert submitting.status == ExternalOperationState.SUBMITTING.value
        assert submitting.attempt == 1
        operation_id = operation.id
        await session.commit()
        with pytest.raises(ExternalOperationConflict, match="fencing"):
            await repository.transition(
                operation_id,
                target=ExternalOperationState.SUBMITTED,
                expected_generation=lease_generation + 1,
                provider_request_id="provider-job-1",
            )

    async with sessions() as session:
        repository = ExternalOperationRepository(session)
        submitted = await repository.transition(
            operation_id,
            target=ExternalOperationState.SUBMITTED,
            expected_generation=lease_generation,
            provider_request_id="provider-job-1",
        )
        assert submitted.status == ExternalOperationState.SUBMITTED.value
        assert submitted.provider_request_id == "provider-job-1"
        with pytest.raises(ValueError, match="transition_not_allowed"):
            await repository.transition(
                operation_id,
                target=ExternalOperationState.SUCCEEDED,
                expected_generation=lease_generation,
            )

    await engine.dispose()
