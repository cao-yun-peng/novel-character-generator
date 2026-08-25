from asyncio import to_thread
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from novel_character_generator.api.app import create_app
from novel_character_generator.api.deps import get_session
from novel_character_generator.application.ports.extraction import (
    ChunkExtractionResult,
    ExpressionDraft,
    MentionDraft,
    ObservationDraft,
    SceneHypothesisDraft,
    TimelineHypothesisDraft,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    DecisionRecordORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    SceneORM,
    StoryEventORM,
    TimelineORM,
)
from novel_character_generator.infrastructure.db.repositories.extraction import (
    is_canonical_timeline_name,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


class TemporalProvider:
    version = "temporal-test-v1"

    async def extract_chunk(self, text: str) -> ChunkExtractionResult:
        name_start = text.index("林舟")
        hair_start = text.index("黑发")
        smile_start = text.index("微笑")
        memory_start = text.index("往昔")
        return ChunkExtractionResult(
            mentions=[
                MentionDraft(
                    text="林舟",
                    canonical_name="林舟",
                    start=name_start,
                    end=name_start + 2,
                    kind="name",
                )
            ],
            observations=[
                ObservationDraft(
                    character_name="林舟",
                    field_path="hair.color",
                    value="black",
                    evidence_quote="黑发",
                    start=hair_start,
                    end=hair_start + 2,
                    confidence=0.98,
                )
            ],
            expression_observations=[
                ExpressionDraft(
                    character_name="林舟",
                    outward_emotion="joy",
                    expression_text="微笑",
                    visible_cues=["嘴角上扬"],
                    start=smile_start,
                    end=smile_start + 2,
                    confidence=0.95,
                )
            ],
            timeline_hypotheses=[
                TimelineHypothesisDraft(
                    name="往昔时间线",
                    canonicality="alternate",
                    evidence_quote="往昔",
                    start=memory_start,
                    end=memory_start + 2,
                    confidence=0.9,
                )
            ],
            scene_hypotheses=[
                SceneHypothesisDraft(
                    label="往昔重逢",
                    start=0,
                    end=len(text),
                    timeline_name="往昔时间线",
                    presentation_mode="flashback",
                    reality_status="canonical",
                    confidence=0.92,
                )
            ],
        )


class RevisedTemporalProvider(TemporalProvider):
    version = "temporal-test-v2"

    async def extract_chunk(self, text: str) -> ChunkExtractionResult:
        result = await super().extract_chunk(text)
        memory_start = text.index("往昔")
        return result.model_copy(
            update={
                "scene_hypotheses": [
                    SceneHypothesisDraft(
                        label="重新识别的往昔重逢",
                        start=memory_start,
                        end=len(text),
                        timeline_name="往昔时间线",
                        presentation_mode="flashback",
                        reality_status="canonical",
                        confidence=0.97,
                    )
                ]
            }
        )


def test_main_timeline_aliases_resolve_to_canonical_timeline() -> None:
    assert is_canonical_timeline_name("main")
    assert is_canonical_timeline_name("Main Timeline")
    assert is_canonical_timeline_name("主线时间线")
    assert not is_canonical_timeline_name("往昔时间线")


@pytest.mark.asyncio
async def test_reanalysis_updates_automatic_scene_when_span_changes(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'scene-reanalysis.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "scene-reanalysis-artifacts")
    text = "第一章\n往昔，林舟仍是黑发，见到故人时微笑。"

    async with sessions() as session:
        ingestion = IngestionService(session, store)
        novel = await ingestion.upload(filename="scene-reanalysis.txt", data=text.encode())
        ingestion_run = await ingestion.create_run(novel.id, "scene-ingestion")
        assert ingestion_run is not None
        await process_ingestion_run(session, store, ingestion_run.id, target_tokens=1_000)

        first_run = await ingestion.create_extraction_run(novel.id, "scene-extraction-v1")
        assert first_run is not None
        await process_extraction_run(session, TemporalProvider(), first_run.id)
        original = await session.scalar(select(SceneORM).where(SceneORM.novel_id == novel.id))
        assert original is not None
        original_id = original.id
        original_event_id = original.event_id

        second_run = await ingestion.create_extraction_run(novel.id, "scene-extraction-v2")
        assert second_run is not None
        await process_extraction_run(session, RevisedTemporalProvider(), second_run.id)

        scenes = list(
            await session.scalars(select(SceneORM).where(SceneORM.novel_id == novel.id))
        )
        assert len(scenes) == 1
        refreshed = scenes[0]
        assert refreshed.id == original_id
        assert refreshed.label == "重新识别的往昔重逢"
        assert refreshed.char_start == text.index("往昔")
        assert refreshed.char_end == len(text)
        assert refreshed.binding_status == "hypothesis"
        assert refreshed.binding_revision == 1
        assert refreshed.event_id == original_event_id
        event = await session.get(StoryEventORM, refreshed.event_id)
        assert event is not None
        assert event.name == "重新识别的往昔重逢"

    await engine.dispose()


@pytest.mark.asyncio
async def test_scene_hypotheses_are_grounded_queryable_and_correctable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'story.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    text = "第一章\n往昔，林舟仍是黑发，见到故人时微笑。"

    async with sessions() as session:
        ingestion = IngestionService(session, store)
        novel = await ingestion.upload(filename="story.txt", data=text.encode())
        ingestion_run = await ingestion.create_run(novel.id, "story-ingestion")
        assert ingestion_run is not None
        await process_ingestion_run(session, store, ingestion_run.id, target_tokens=1_000)
        extraction_run = await ingestion.create_extraction_run(novel.id, "story-extraction")
        assert extraction_run is not None
        await process_extraction_run(session, TemporalProvider(), extraction_run.id)
        scene = await session.scalar(select(SceneORM).where(SceneORM.novel_id == novel.id))
        observation = await session.scalar(select(FeatureObservationORM))
        expression = await session.scalar(select(ExpressionObservationORM))
        timelines = list(
            await session.scalars(select(TimelineORM).where(TimelineORM.novel_id == novel.id))
        )
        assert scene is not None
        assert scene.presentation_mode == "flashback"
        assert scene.source_chunk_id is not None
        assert observation is not None and observation.scene_id == scene.id
        assert observation.temporal_scope["presentation_mode"] == "flashback"
        assert expression is not None and expression.scene_id == scene.id
        canonical = next(item for item in timelines if item.canonicality == "canonical")
        scene_id = scene.id
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
            headers = {"X-API-Key": "user-secret"}
            timeline_response = await client.get(
                f"/api/v1/novels/{novel_id}/timelines", headers=headers
            )
            event_response = await client.get(
                f"/api/v1/novels/{novel_id}/events", headers=headers
            )
            scene_response = await client.get(
                f"/api/v1/novels/{novel_id}/scenes", headers=headers
            )
            assert timeline_response.status_code == 200
            assert len(timeline_response.json()) == 2
            assert event_response.status_code == 200
            assert event_response.json()[0]["name"] == "往昔重逢"
            assert scene_response.status_code == 200
            assert scene_response.json()[0]["binding_revision"] == 1

            correction_headers = {
                **headers,
                "If-Match": '"1"',
                "X-Actor-ID": "editor-1",
            }
            correction = await client.put(
                f"/api/v1/scenes/{scene_id}/temporal-binding",
                headers=correction_headers,
                json={
                    "timeline_id": str(canonical.id),
                    "event_id": None,
                    "presentation_mode": "direct",
                    "reality_status": "canonical",
                },
            )
            assert correction.status_code == 200
            assert correction.json()["binding_status"] == "corrected"
            assert correction.json()["binding_revision"] == 2
            stale = await client.put(
                f"/api/v1/scenes/{scene_id}/temporal-binding",
                headers=correction_headers,
                json={
                    "timeline_id": str(canonical.id),
                    "event_id": None,
                    "presentation_mode": "direct",
                    "reality_status": "canonical",
                },
            )
            assert stale.status_code == 409
            assert stale.json()["code"] == "scene_binding_revision_conflict"
    finally:
        get_settings.cache_clear()

    async with sessions() as session:
        decision = await session.scalar(
            select(DecisionRecordORM).where(
                DecisionRecordORM.subject_id == scene_id,
                DecisionRecordORM.decision_kind == "temporal_binding",
            )
        )
        rebound_observation = await session.scalar(select(FeatureObservationORM))
        assert decision is not None
        assert decision.decision["actor_id"] == "editor-1"
        assert rebound_observation is not None
        assert rebound_observation.temporal_scope["timeline_id"] == str(canonical.id)
        assert rebound_observation.temporal_scope["presentation_mode"] == "direct"

        replacement = await IngestionService(session, store).create_extraction_run(
            novel_id, "story-extraction-v2"
        )
        assert replacement is not None
        await process_extraction_run(session, RevisedTemporalProvider(), replacement.id)

        scenes = list(
            await session.scalars(select(SceneORM).where(SceneORM.novel_id == novel_id))
        )
        assert len(scenes) == 1
        refreshed_scene = scenes[0]
        assert refreshed_scene.id == scene_id
        assert refreshed_scene.label == "重新识别的往昔重逢"
        assert refreshed_scene.char_start == text.index("往昔")
        assert refreshed_scene.char_end == len(text)
        assert refreshed_scene.binding_status == "corrected"
        assert refreshed_scene.binding_revision == 2
        assert refreshed_scene.timeline_id == canonical.id
        assert refreshed_scene.event_id is None
        assert refreshed_scene.presentation_mode == "direct"
        assert refreshed_scene.reality_status == "canonical"

    await engine.dispose()
