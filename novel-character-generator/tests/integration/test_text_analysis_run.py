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
from novel_character_generator.application.ports.extraction import (
    DetailedExtractionResult,
    ExtractionCallMetadata,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.llm.mock import (
    MockEntityResolutionProvider,
    MockExtractionProvider,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.handlers.appearance_aggregation import (
    process_appearance_aggregation_run,
)
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run
from novel_character_generator.workers.handlers.phase_resolution import (
    process_phase_resolution_run,
)


class RawResponseMockProvider(MockExtractionProvider):
    async def extract_chunk_detailed(self, text: str) -> DetailedExtractionResult:
        message = '{"entities": [], "visual_candidates": []}'
        return DetailedExtractionResult(
            output=self.extract_visual_candidates(text),
            metadata=ExtractionCallMetadata(
                wire_api="chat_completions",
                provider_request_id="raw-response-test",
                response_model="mock-raw-v1",
                status="completed",
                finish_reason="stop",
                latency_ms=3,
            ),
            raw_message_content=message,
            raw_response={
                "id": "raw-response-test",
                "model": "mock-raw-v1",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": message}}
                ],
            },
        )


class RawResponseMockEntityProvider(MockEntityResolutionProvider):
    last_raw_message_content = '{"decisions": []}'
    last_raw_response = {
        "id": "entity-raw-response-test",
        "model": "mock-entity-raw-v1",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": last_raw_message_content},
            }
        ],
    }


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
    monkeypatch.setenv("LLM_RAW_RESPONSE_CAPTURE_ENABLED", "true")
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

            novels_response = await client.get(
                "/api/v1/novels", headers={"X-API-Key": "user-secret"}
            )
            assert novels_response.status_code == 200
            assert novels_response.json()[0]["id"] == str(novel_id)

            runs_response = await client.get(
                f"/api/v1/novels/{novel_id}/runs",
                headers={"X-API-Key": "user-secret"},
            )
            assert runs_response.status_code == 200
            assert runs_response.json()[0]["id"] == str(run_id)
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
        await process_extraction_run(
            session,
            RawResponseMockProvider(),
            run_id,
            entity_provider=RawResponseMockEntityProvider(),
            capture_raw_responses=True,
        )
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
            ("extract_characters", "succeeded"),
            ("resolve_character_phases", "queued"),
        ]
        await process_phase_resolution_run(session, run_id)
        steps = list(
            await session.scalars(
                select(PipelineStepORM)
                .where(PipelineStepORM.run_id == run_id)
                .order_by(PipelineStepORM.created_at)
            )
        )
        assert [(step.step_key, step.status) for step in steps] == [
            ("normalize_and_chunk", "succeeded"),
            ("extract_characters", "succeeded"),
            ("resolve_character_phases", "succeeded"),
            ("aggregate_appearance", "queued"),
        ]
        await process_appearance_aggregation_run(session, run_id)
        run = await session.get(PipelineRunORM, run_id)
        assert run is not None and run.status == "succeeded"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"X-API-Key": "user-secret"}
        inspection = await client.get(
            f"/api/v1/runs/{run_id}/inspection", headers=headers
        )
        assert inspection.status_code == 200
        body = inspection.json()
        assert body["schema_version"] == "run-inspector-v1"
        assert [stage["key"] for stage in body["stages"]] == ["r1", "r2", "r3"]
        assert [stage["status"] for stage in body["stages"]] == [
            "succeeded",
            "succeeded",
            "succeeded",
        ]
        assert "content" not in body
        r1_output = body["stages"][0]["outputs"][0]
        r2_output = body["stages"][1]["outputs"][0]
        r2_convergence_output = next(
            item for item in body["stages"][1]["outputs"] if item["kind"] == "r2_convergence"
        )
        assert body["stages"][1]["metrics"]["memory_selection_calls"] == 1
        assert body["stages"][1]["metrics"]["max_memory_records_before"] == 0
        assert body["stages"][1]["metrics"]["convergence_frontier_batches"] == 1
        assert body["stages"][1]["metrics"]["convergence_provider_omitted_mentions"] == 0
        assert body["stages"][1]["metrics"]["convergence_shards_total"] == 1
        assert body["stages"][1]["metrics"]["max_convergence_shard_records"] == 1
        assert body["stages"][1]["metrics"]["max_convergence_shard_mentions"] == 1
        assert body["stages"][1]["metrics"]["convergence_provider_calls_total"] == 1
        assert body["stages"][1]["metrics"]["convergence_repair_attempts_total"] == 0
        assert body["stages"][1]["metrics"]["convergence_fallback_mentions"] == 0

        r1_detail = await client.get(
            f"/api/v1/runs/{run_id}/inspection/outputs/"
            f"{r1_output['kind']}/{r1_output['id']}",
            headers=headers,
        )
        assert r1_detail.status_code == 200
        assert r1_detail.json()["kind"] == "r1_chunk"
        assert "visual_candidates" in r1_detail.json()["output"]
        assert "facts" in r1_detail.json()["intermediate"]
        assert r1_detail.json()["input_hash"]
        assert r1_detail.json()["trace"]["result_hash"]
        assert "content" not in r1_detail.json()["trace"]
        assert "raw_response" not in r1_detail.json()

        raw_denied = await client.get(
            f"/api/v1/runs/{run_id}/inspection/outputs/r1_chunk/"
            f"{r1_output['id']}/raw-response",
            headers=headers,
        )
        assert raw_denied.status_code == 403

        raw_detail = await client.get(
            f"/api/v1/runs/{run_id}/inspection/outputs/r1_chunk/"
            f"{r1_output['id']}/raw-response",
            headers={"X-API-Key": "admin-secret"},
        )
        assert raw_detail.status_code == 200
        assert raw_detail.json()["schema_version"] == "raw-model-response-v1"
        assert raw_detail.json()["message_content"] == (
            '{"entities": [], "visual_candidates": []}'
        )
        assert raw_detail.json()["response_payload"]["id"] == "raw-response-test"
        assert len(raw_detail.json()["payload_hash"]) == 64

        r2_detail = await client.get(
            f"/api/v1/runs/{run_id}/inspection/outputs/"
            f"{r2_output['kind']}/{r2_output['id']}",
            headers=headers,
        )
        assert r2_detail.status_code == 200
        assert r2_detail.json()["kind"] == "r2_chunk"
        assert r2_detail.json()["input_hash"]
        assert "decisions" in r2_detail.json()["output"]
        memory_trace = r2_detail.json()["trace"]["memory_selection"]
        assert memory_trace["policy"] == "entity-memory-selection-v1"
        assert memory_trace["records_before"] == 0
        assert memory_trace["records_selected"] == 0
        assert memory_trace["records_after"] == 1
        assert memory_trace["records_added"] == 1
        assert memory_trace["status_after"] == {
            "stable": 0,
            "provisional": 1,
            "unresolved": 0,
        }
        assert "evidence_quotes" not in memory_trace
        assert "chunk_text" not in memory_trace

        convergence_detail = await client.get(
            f"/api/v1/runs/{run_id}/inspection/outputs/"
            f"{r2_convergence_output['kind']}/{r2_convergence_output['id']}",
            headers=headers,
        )
        assert convergence_detail.status_code == 200
        frontier_trace = convergence_detail.json()["trace"]["convergence_frontier"]
        assert frontier_trace["policy"] == "entity-convergence-frontier-v1"
        assert frontier_trace["frontier_records"] == 1
        assert frontier_trace["provider_omitted_mentions"] == 0
        assert "evidence_quotes" not in frontier_trace
        sharding_trace = convergence_detail.json()["trace"]["convergence_sharding"]
        assert sharding_trace["policy"] == "entity-convergence-shard-v2"
        assert sharding_trace["shard_count"] == 1
        assert sharding_trace["budget"]["max_records"] == 16
        assert sharding_trace["input_token_overhead"] > 0
        assert sharding_trace["provider_calls"] == 1
        assert sharding_trace["repair_attempts"] == 0
        assert sharding_trace["fallback_mentions"] == 0
        assert "evidence_quotes" not in sharding_trace

        r2_raw_detail = await client.get(
            f"/api/v1/runs/{run_id}/inspection/outputs/r2_chunk/"
            f"{r2_output['id']}/raw-response",
            headers={"X-API-Key": "admin-secret"},
        )
        assert r2_raw_detail.status_code == 200
        assert r2_raw_detail.json()["kind"] == "r2_chunk"
        assert (
            r2_raw_detail.json()["response_payload"]["id"]
            == "entity-raw-response-test"
        )

        mismatched = await client.get(
            f"/api/v1/runs/{run_id}/inspection/outputs/"
            f"r3_character/{r1_output['id']}",
            headers=headers,
        )
        assert mismatched.status_code == 404

    await engine.dispose()
