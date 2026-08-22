from asyncio import to_thread
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
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
from novel_character_generator.application.ports.agent_runtime import (
    ApprovalRequest,
    ToolCallRequest,
)
from novel_character_generator.application.services.approval_service import ApprovalService
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    AgentRunORM,
    AgentTurnORM,
    PipelineRunORM,
    PipelineStepORM,
    RunEventORM,
    ToolCallORM,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings


@pytest.mark.asyncio
async def test_approval_cas_resume_and_agent_trajectory_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'approval.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)

    async with sessions() as session:
        service = IngestionService(session, LocalArtifactStore(tmp_path / "artifacts"))
        novel = await service.upload(filename="approval.txt", data="第一章".encode())
        run = await service.create_run(novel.id, "approval-run")
        assert run is not None
        step = await session.scalar(
            select(PipelineStepORM).where(PipelineStepORM.run_id == run.id)
        )
        assert step is not None
        step.status = "running"
        step.lease_generation = 3
        step.lease_owner = "worker-1"
        run.status = "running"
        agent_run_id = uuid4()
        agent_run = AgentRunORM(
            id=agent_run_id,
            pipeline_step_id=step.id,
            agent_id="review-agent",
            agent_version="v1",
            status="waiting_approval",
            budget={"max_cost": "1.0", "max_turns": 3},
            context_hash="c" * 64,
            final_output_hash=None,
            stop_reason="approval_required",
            attempt=1,
            agent_spec_snapshot={"agent_id": "review-agent", "version": "v1"},
            tool_spec_versions={"publish": "v1"},
            prompt_version="prompt-v1",
            model_policy="reasoning-medium",
            output_schema="ReviewFinding",
            permission="admin",
            evaluation_version="eval-v1",
            started_at=now,
            completed_at=now,
            input_tokens=120,
            output_tokens=30,
            total_cost=Decimal("0.12"),
            latency_ms=250,
            created_at=now,
            updated_at=now,
        )
        session.add(agent_run)
        session.add(
            AgentTurnORM(
                id=uuid4(),
                agent_run_id=agent_run_id,
                turn_number=1,
                input_context_hash="c" * 64,
                output_summary={"kind": "approval_request"},
                usage={"input_tokens": 120, "output_tokens": 30},
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            ToolCallORM(
                id=uuid4(),
                agent_run_id=agent_run_id,
                call_id="publish-1",
                tool_name="publish",
                tool_version="v1",
                input_hash="a" * 64,
                output_hash=None,
                status="approval_required",
                side_effect=True,
                duration_ms=0,
                error_code=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        created = await ApprovalService(session).create_request(
            pipeline_step_id=step.id,
            expected_generation=3,
            requested_by_agent_run_id=agent_run_id,
            request=ApprovalRequest(
                tool_call=ToolCallRequest(
                    call_id="publish-1",
                    tool_name="publish",
                    arguments={"profile_id": "profile-1"},
                ),
                action={"tool": "publish", "arguments": {"profile_id": "profile-1"}},
                estimated_cost=Decimal("0.2"),
                options=["approve", "reject", "modify", "defer"],
                expires_at=now + timedelta(hours=1),
            ),
        )
        approval_id = created.approval.id
        run_id = run.id
        step_id = step.id

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
            denied = await client.get(
                "/api/v1/approvals", headers={"X-API-Key": "user-secret"}
            )
            assert denied.status_code == 403
            assert denied.json()["code"] == "admin_api_key_required"

            page = await client.get(
                "/api/v1/approvals", headers={"X-API-Key": "admin-secret"}
            )
            assert page.status_code == 200
            assert page.json()["items"][0]["revision"] == 1

            agent_runs = await client.get(
                f"/api/v1/runs/{run_id}/agent-runs",
                headers={"X-API-Key": "user-secret"},
            )
            assert agent_runs.status_code == 200
            assert agent_runs.json()[0]["prompt_version"] == "prompt-v1"
            trajectory = await client.get(
                f"/api/v1/agent-runs/{agent_run_id}",
                headers={"X-API-Key": "user-secret"},
            )
            assert trajectory.status_code == 200
            assert trajectory.json()["turns"][0]["turn_number"] == 1
            assert trajectory.json()["tool_calls"][0]["input_hash"] == "a" * 64

            resolve_headers = {
                "X-API-Key": "admin-secret",
                "X-Actor-ID": "reviewer-1",
                "If-Match": '"1"',
            }
            resolved = await client.post(
                f"/api/v1/approvals/{approval_id}/resolve",
                headers=resolve_headers,
                json={"decision": "approve"},
            )
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "approved"
            assert resolved.json()["revision"] == 2
            duplicate = await client.post(
                f"/api/v1/approvals/{approval_id}/resolve",
                headers=resolve_headers,
                json={"decision": "approve"},
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["code"] == "approval_already_resolved"
    finally:
        get_settings.cache_clear()

    async with sessions() as session:
        step = await session.get(PipelineStepORM, step_id)
        run = await session.get(PipelineRunORM, run_id)
        events = list(
            await session.scalars(
                select(RunEventORM)
                .where(RunEventORM.run_id == run_id)
                .order_by(RunEventORM.sequence)
            )
        )
        assert step is not None and step.status == "queued"
        assert run is not None and run.status == "queued"
        assert [event.event_type for event in events][-2:] == [
            "approval.requested",
            "approval.resolved",
        ]

    await engine.dispose()
