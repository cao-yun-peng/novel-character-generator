from asyncio import to_thread
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.agent_runtime import (
    ApprovalRequest,
    ToolCallRequest,
)
from novel_character_generator.application.services.approval_service import ApprovalService
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore


@pytest.mark.asyncio
async def test_deferred_approval_can_later_be_rejected(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'approval-decisions.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)

    async with sessions() as session:
        ingestion = IngestionService(session, LocalArtifactStore(tmp_path / "artifacts"))
        novel = await ingestion.upload(filename="decision.txt", data="第一章 决策".encode())
        run = await ingestion.create_run(novel.id, "approval-decisions")
        assert run is not None
        step = await session.scalar(
            select(PipelineStepORM).where(PipelineStepORM.run_id == run.id)
        )
        assert step is not None
        step.status = "running"
        step.lease_generation = 1
        run.status = "running"
        await session.commit()
        created = await ApprovalService(session).create_request(
            pipeline_step_id=step.id,
            expected_generation=1,
            request=ApprovalRequest(
                tool_call=ToolCallRequest(
                    call_id="delete-1",
                    tool_name="delete",
                    arguments={"target": "draft"},
                ),
                action={"tool": "delete", "arguments": {"target": "draft"}},
                options=["approve", "reject", "modify", "defer"],
                expires_at=now + timedelta(hours=1),
            ),
        )
        deferred = await ApprovalService(session).resolve(
            created.approval.id,
            decision="defer",
            expected_revision=1,
            recovery_token=created.recovery_token,
            resolved_by="reviewer-1",
            defer_until=now + timedelta(hours=2),
        )
        assert deferred.status == "pending"
        assert deferred.decision == "defer"
        assert deferred.revision == 2
        rejected = await ApprovalService(session).resolve(
            created.approval.id,
            decision="reject",
            expected_revision=2,
            recovery_token=created.recovery_token,
            resolved_by="reviewer-1",
        )
        assert rejected.status == "rejected"
        assert rejected.revision == 3

    async with sessions() as session:
        step = await session.get(PipelineStepORM, step.id)
        run = await session.get(PipelineRunORM, run.id)
        assert step is not None and step.status == "cancelled"
        assert run is not None and run.status == "cancelled"

    await engine.dispose()
