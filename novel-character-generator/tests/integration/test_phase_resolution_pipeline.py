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
    VisualCandidateExtractionResult,
    VisualEntityCandidate,
    VisualFactCandidate,
    VisualTemporalSignal,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    CharacterLifePhaseORM,
    FeatureObservationORM,
    ObservationScopeBindingORM,
    PipelineStepORM,
    TemporalSignalORM,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run
from novel_character_generator.workers.handlers.phase_resolution import (
    process_phase_resolution_run,
)


class PhaseAwareVisualProvider:
    version = "phase-aware-visual-v1"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        assert "前世的沈砚" in text
        return VisualCandidateExtractionResult(
            entities=[
                VisualEntityCandidate(
                    local_id="e1",
                    representative_name="沈砚",
                    mention_quote="沈砚",
                    mention_kind="name",
                    confidence=1.0,
                )
            ],
            visual_candidates=[
                VisualFactCandidate(
                    entity_ref="e1",
                    field_path="hair.color",
                    value="黑色",
                    evidence_quote="黑发",
                    confidence=1.0,
                    temporal_signals=[
                        VisualTemporalSignal(
                            kind="life_phase",
                            label="前世",
                            evidence_quote="前世",
                        )
                    ],
                ),
                VisualFactCandidate(
                    entity_ref="e1",
                    field_path="clothing.color",
                    value="白色",
                    evidence_quote="白衣",
                    confidence=1.0,
                    temporal_signals=[
                        VisualTemporalSignal(
                            kind="time_jump",
                            label="三年后",
                            evidence_quote="三年后",
                        )
                    ],
                ),
            ],
        )


@pytest.mark.asyncio
async def test_r3_activates_final_scope_and_keeps_ambiguous_fact_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'phase-resolution.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(
            filename="phase.txt",
            data="第一章\n前世的沈砚留着黑发，三年后穿上白衣。".encode(),
        )
        ingestion = await service.create_run(novel.id, "phase-ingest")
        assert ingestion is not None
        await process_ingestion_run(session, store, ingestion.id, target_tokens=1_000)
        extraction = await service.create_extraction_run(novel.id, "phase-extract")
        assert extraction is not None
        await process_extraction_run(session, PhaseAwareVisualProvider(), extraction.id)

        before = list(
            await session.scalars(
                select(FeatureObservationORM).order_by(FeatureObservationORM.field_path)
            )
        )
        assert [item.record_status for item in before] == ["pending", "pending"]

        await process_phase_resolution_run(session, extraction.id)

        observations = list(
            await session.scalars(
                select(FeatureObservationORM).order_by(FeatureObservationORM.field_path)
            )
        )
        assert [(item.field_path, item.record_status) for item in observations] == [
            ("clothing.color", "pending"),
            ("hair.color", "active"),
        ]
        assert observations[1].temporal_scope["life_phase_key"] == "past_life"

        phases = list(await session.scalars(select(CharacterLifePhaseORM)))
        assert [(phase.phase_key, phase.status) for phase in phases] == [("past_life", "active")]
        bindings = list(
            await session.scalars(
                select(ObservationScopeBindingORM).order_by(
                    ObservationScopeBindingORM.observation_id
                )
            )
        )
        assert {binding.status for binding in bindings} == {"final", "needs_review"}
        review_binding = next(binding for binding in bindings if binding.status == "needs_review")
        assert review_binding.temporal_scope["scope_review_reasons"] == ["unresolved_time_jump"]

        signals = list(await session.scalars(select(TemporalSignalORM)))
        assert {signal.resolution_status for signal in signals} == {"bound"}
        assert all(signal.feature_observation_ids for signal in signals)
        aggregate = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == extraction.id,
                PipelineStepORM.step_key == "aggregate_appearance",
            )
        )
        assert aggregate is not None and aggregate.status == "queued"
        novel_id = novel.id
        character_id = phases[0].character_id
        phase_id = phases[0].id

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
            review = await client.get(
                f"/api/v1/novels/{novel_id}/temporal-review",
                headers=headers,
            )
            assert review.status_code == 200
            assert len(review.json()["scope_bindings_needing_review"]) == 1

            phase_list = await client.get(
                f"/api/v1/characters/{character_id}/life-phases",
                headers=headers,
            )
            assert phase_list.status_code == 200
            assert phase_list.json()[0]["phase_key"] == "past_life"

            inspection = await client.get(
                f"/api/v1/runs/{extraction.id}/inspection",
                headers=headers,
            )
            assert inspection.status_code == 200
            r3 = inspection.json()["stages"][2]
            assert r3["key"] == "r3"
            assert r3["status"] == "succeeded"
            assert r3["metrics"]["life_phases"] == 1
            assert r3["metrics"]["needs_review_bindings"] == 1
            assert r3["attention_reasons"] == [
                "scope_review_required",
                "pending_observations_present",
            ]
            r3_output = r3["outputs"][0]
            r3_detail = await client.get(
                f"/api/v1/runs/{extraction.id}/inspection/outputs/"
                f"{r3_output['kind']}/{r3_output['id']}",
                headers=headers,
            )
            assert r3_detail.status_code == 200
            assert r3_detail.json()["kind"] == "r3_character"
            assert r3_detail.json()["version"] == "character-phase-resolution-v1"
            assert "scope_decisions" in r3_detail.json()["output"]

            correction = await client.post(
                f"/api/v1/characters/{character_id}/life-phases/{phase_id}/resolve",
                headers={
                    **headers,
                    "If-Match": '"1"',
                    "X-Actor-ID": "editor-1",
                },
                json={
                    "label": "前世阶段",
                    "start_chapter_ordinal": 0,
                    "end_chapter_ordinal": 2,
                    "status": "active",
                    "reason": "人工核对章节范围",
                },
            )
            assert correction.status_code == 200
            assert correction.json()["revision"] == 2
            assert correction.json()["resolver_version"] == "manual-phase-resolution-v1"
    finally:
        get_settings.cache_clear()

    await engine.dispose()
