from asyncio import to_thread
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from novel_character_generator.api.app import create_app
from novel_character_generator.api.deps import get_session
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.llm.mock import MockExtractionProvider
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


@pytest.mark.asyncio
async def test_public_run_endpoint_executes_ingestion_then_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'analysis-run.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")

    async with sessions() as session:
        novel = await IngestionService(session, store).upload(
            filename="analysis.txt",
            data="第一章\n林舟走进庭院。".encode(),
        )
        novel_id = novel.id

    monkeypatch.setenv("USER_API_KEY", "user-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/novels/{novel_id}/runs",
                headers={
                    "X-API-Key": "user-secret",
                    "Idempotency-Key": "full-analysis-1",
                },
            )
            assert response.status_code == 202
            assert response.json()["run_type"] == "text_analysis"
            run_id = UUID(response.json()["id"])
    finally:
        get_settings.cache_clear()

    async with sessions() as session:
        await process_ingestion_run(session, store, run_id, target_tokens=1_000)
        run = await session.get(PipelineRunORM, run_id)
        steps = list(
            await session.scalars(
                select(PipelineStepORM)
                .where(PipelineStepORM.run_id == run_id)
                .order_by(PipelineStepORM.created_at)
            )
        )
        assert run is not None and run.status == "queued"
        assert [(step.step_key, step.status) for step in steps] == [
            ("normalize_and_chunk", "succeeded"),
            ("extract_characters", "queued"),
        ]
        await process_extraction_run(session, MockExtractionProvider(), run_id)
        run = await session.get(PipelineRunORM, run_id)
        steps = list(
            await session.scalars(
                select(PipelineStepORM)
                .where(PipelineStepORM.run_id == run_id)
                .order_by(PipelineStepORM.created_at)
            )
        )
        assert run is not None and run.status == "succeeded"
        assert all(step.status == "succeeded" for step in steps)

    await engine.dispose()
