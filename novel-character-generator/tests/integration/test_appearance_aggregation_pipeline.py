from asyncio import to_thread
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from novel_character_generator.api.app import create_app
from novel_character_generator.api.deps import get_session
from novel_character_generator.application.ports.extraction import (
    ChunkExtractionResult,
    ObservationDraft,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterORM,
    CharacterRenderProfileORM,
    PipelineRunORM,
    PipelineStepORM,
    RunEventORM,
)
from novel_character_generator.infrastructure.llm.mock import MockExtractionProvider
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.handlers.appearance_aggregation import (
    process_appearance_aggregation_run,
)
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


class ConflictingAppearanceProvider:
    version = "conflicting-appearance-v1"

    async def extract_chunk(self, text: str) -> ChunkExtractionResult:
        black_start = text.index("黑眼")
        blue_start = text.index("蓝眼")
        return ChunkExtractionResult(
            observations=[
                ObservationDraft(
                    character_name="林舟",
                    field_path="face.eye_color",
                    value="black",
                    evidence_quote="黑眼",
                    start=black_start,
                    end=black_start + len("黑眼"),
                    confidence=1.0,
                ),
                ObservationDraft(
                    character_name="林舟",
                    field_path="face.eye_color",
                    value="blue",
                    evidence_quote="蓝眼",
                    start=blue_start,
                    end=blue_start + len("蓝眼"),
                    confidence=1.0,
                ),
            ]
        )


@pytest.mark.asyncio
async def test_real_observations_form_idempotent_reviewable_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'appearance-aggregation.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    text = "第一章\n少年沈砚披着旧青氅。他左眼下有一颗浅痣。"

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="appearance.txt", data=text.encode())
        run = await service.create_analysis_run(novel.id, "appearance-analysis")
        assert run is not None
        await process_ingestion_run(session, store, run.id, target_tokens=1_000)
        await process_extraction_run(session, MockExtractionProvider(), run.id)
        await process_appearance_aggregation_run(session, run.id)

        character = await session.scalar(
            select(CharacterORM).where(
                CharacterORM.novel_id == novel.id,
                CharacterORM.canonical_name == "沈砚",
            )
        )
        assert character is not None
        profile = await session.scalar(
            select(CharacterRenderProfileORM).where(
                CharacterRenderProfileORM.character_id == character.id
            )
        )
        states = list(
            await session.scalars(
                select(CharacterAppearanceStateORM).where(
                    CharacterAppearanceStateORM.character_id == character.id
                )
            )
        )
        assert profile is not None
        assert profile.status == "draft"
        assert profile.input_fingerprint is not None
        assert profile.identity_anchor["face"]["distinctive_mark"] == "左眼下有一颗浅痣"
        assert states
        assert all(item.aggregation_fingerprint is not None for item in states)
        counts_before = (
            await session.scalar(select(func.count()).select_from(CharacterAppearanceStateORM)),
            await session.scalar(select(func.count()).select_from(CharacterConflictORM)),
            await session.scalar(select(func.count()).select_from(CharacterRenderProfileORM)),
        )

        aggregation_step = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == run.id,
                PipelineStepORM.step_key == "aggregate_appearance",
            )
        )
        persisted_run = await session.get(PipelineRunORM, run.id)
        assert aggregation_step is not None and persisted_run is not None
        aggregation_step.status = "queued"
        aggregation_step.cursor = {
            "schema_version": "v1",
            "source_document_version_id": str(profile.source_document_version_id),
            "completed_character_ids": [],
        }
        persisted_run.status = "queued"
        persisted_run.completed_at = None
        await session.commit()
        await process_appearance_aggregation_run(session, run.id)
        counts_after = (
            await session.scalar(select(func.count()).select_from(CharacterAppearanceStateORM)),
            await session.scalar(select(func.count()).select_from(CharacterConflictORM)),
            await session.scalar(select(func.count()).select_from(CharacterRenderProfileORM)),
        )
        assert counts_after == counts_before
        event_types = list(
            await session.scalars(
                select(RunEventORM.event_type)
                .where(RunEventORM.run_id == run.id)
                .order_by(RunEventORM.sequence)
            )
        )
        assert "appearance.profile.drafted" in event_types
        assert "appearance.aggregation.unchanged" in event_types
        character_id = character.id

    monkeypatch.setenv("USER_API_KEY", "user-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"X-API-Key": "user-secret"}
            profile_response = await client.get(
                f"/api/v1/characters/{character_id}/render-profile", headers=headers
            )
            states_response = await client.get(
                f"/api/v1/characters/{character_id}/appearance-states", headers=headers
            )
            observations_response = await client.get(
                f"/api/v1/characters/{character_id}/observations", headers=headers
            )
            assert profile_response.status_code == 200
            assert profile_response.json()["status"] == "draft"
            assert states_response.status_code == 200
            assert states_response.json()
            assert observations_response.status_code == 200
            observation = observations_response.json()[0]
            assert "chapter_ordinal" in observation
            assert "temporal_scope" in observation
            assert "life_phase_key" in observation
            assert "is_visual" in observation
            assert "visual_category" in observation
    finally:
        get_settings.cache_clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_scope_conflict_blocks_automatic_profile_approval(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'appearance-conflict.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts-conflict")

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(
            filename="conflict.txt", data="第一章\n林舟有黑眼，也被写成蓝眼。".encode()
        )
        run = await service.create_analysis_run(novel.id, "appearance-conflict")
        assert run is not None
        await process_ingestion_run(session, store, run.id, target_tokens=1_000)
        await process_extraction_run(session, ConflictingAppearanceProvider(), run.id)
        await process_appearance_aggregation_run(session, run.id)

        character = await session.scalar(
            select(CharacterORM).where(CharacterORM.canonical_name == "林舟")
        )
        assert character is not None
        profile = await session.scalar(
            select(CharacterRenderProfileORM).where(
                CharacterRenderProfileORM.character_id == character.id
            )
        )
        conflicts = list(
            await session.scalars(
                select(CharacterConflictORM).where(
                    CharacterConflictORM.character_id == character.id,
                    CharacterConflictORM.status == "pending",
                )
            )
        )
        assert profile is not None and profile.status == "needs_review"
        assert len(conflicts) == 1
        assert conflicts[0].field_path == "face.eye_color"
        assert set(conflicts[0].candidate_values) == {"black", "blue"}

    await engine.dispose()
