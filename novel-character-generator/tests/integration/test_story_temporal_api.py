from asyncio import to_thread
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from novel_character_generator.api.app import create_app
from novel_character_generator.api.deps import get_session
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    DecisionRecordORM,
    SceneORM,
    StoryEventORM,
    TextChunkORM,
    TimelineORM,
)
from novel_character_generator.infrastructure.db.repositories.extraction import (
    ExtractionRepository,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


@pytest.mark.asyncio
async def test_historical_scene_is_queryable_and_correctable_without_v2_extractor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'story.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")

    async with sessions() as session:
        ingestion = IngestionService(session, store)
        novel = await ingestion.upload(
            filename="story.txt",
            data="第一章\n往昔，林舟仍是黑发。".encode(),
        )
        run = await ingestion.create_run(novel.id, "story-ingestion")
        assert run is not None
        await process_ingestion_run(session, store, run.id, target_tokens=1_000)
        chunk = await session.scalar(select(TextChunkORM))
        assert chunk is not None
        canonical = await ExtractionRepository(session).canonical_timeline(novel.id)
        historical = TimelineORM(
            id=uuid4(),
            novel_id=novel.id,
            name="往昔时间线",
            parent_timeline_id=canonical.id,
            branch_event_id=None,
            canonicality="alternate",
        )
        session.add(historical)
        await session.flush()
        event = StoryEventORM(
            id=uuid4(),
            timeline_id=historical.id,
            name="往昔重逢",
            story_order=Decimal(1),
            starts_at=None,
            ends_at=None,
        )
        session.add(event)
        await session.flush()
        now = datetime.now(UTC)
        scene = SceneORM(
            id=uuid4(),
            novel_id=novel.id,
            timeline_id=historical.id,
            event_id=event.id,
            chapter_ordinal=0,
            narrative_order=1,
            point_of_view_character_id=None,
            label="往昔重逢",
            source_document_version_id=chunk.source_document_version_id,
            source_chunk_id=chunk.id,
            char_start=0,
            char_end=len(chunk.content),
            presentation_mode="flashback",
            reality_status="canonical",
            confidence=0.92,
            binding_status="hypothesis",
            binding_revision=1,
            created_by_run_id=run.id,
            created_at=now,
            updated_at=now,
        )
        session.add(scene)
        await session.commit()
        novel_id = novel.id
        scene_id = scene.id
        canonical_id = canonical.id

    monkeypatch.setenv("USER_API_KEY", "user-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            headers = {"X-API-Key": "user-secret"}
            timelines = await client.get(
                f"/api/v1/novels/{novel_id}/timelines",
                headers=headers,
            )
            scenes = await client.get(
                f"/api/v1/novels/{novel_id}/scenes",
                headers=headers,
            )
            assert timelines.status_code == 200
            assert len(timelines.json()) == 2
            assert scenes.status_code == 200
            assert scenes.json()[0]["presentation_mode"] == "flashback"

            correction = await client.put(
                f"/api/v1/scenes/{scene_id}/temporal-binding",
                headers={
                    **headers,
                    "If-Match": '"1"',
                    "X-Actor-ID": "editor-1",
                },
                json={
                    "timeline_id": str(canonical_id),
                    "event_id": None,
                    "presentation_mode": "direct",
                    "reality_status": "canonical",
                },
            )
            assert correction.status_code == 200
            assert correction.json()["binding_status"] == "corrected"
            assert correction.json()["binding_revision"] == 2
    finally:
        get_settings.cache_clear()

    async with sessions() as session:
        decision = await session.scalar(
            select(DecisionRecordORM).where(
                DecisionRecordORM.subject_id == scene_id,
                DecisionRecordORM.decision_kind == "temporal_binding",
            )
        )
        assert decision is not None
        assert decision.decision["actor_id"] == "editor-1"

    await engine.dispose()
