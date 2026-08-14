from asyncio import to_thread
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.agents.structured_runtime import (
    RegisteredTool,
    StructuredCallAgentRuntime,
    ToolRegistry,
)
from novel_character_generator.application.ports.agent_runtime import (
    AgentContextPacket,
    AgentHistoryEntry,
    AgentModelTurn,
    AgentSpec,
    ToolCallRequest,
    ToolPermission,
    ToolSpec,
)
from novel_character_generator.application.services.agent_execution_service import (
    AgentExecutionService,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    AgentRunORM,
    AgentTurnORM,
    HumanApprovalORM,
    PipelineStepORM,
    ToolCallORM,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import Settings


class PublishInput(BaseModel):
    profile_id: str


class PublishOutput(BaseModel):
    published: bool


class ReviewOutput(BaseModel):
    accepted: bool


class ApprovalModel:
    async def generate_turn(
        self,
        *,
        spec: AgentSpec,
        context: AgentContextPacket,
        history: list[AgentHistoryEntry],
        tools: list[ToolSpec],
    ) -> AgentModelTurn:
        del spec, context, history, tools
        return AgentModelTurn(
            tool_calls=[
                ToolCallRequest(
                    call_id="publish-1",
                    tool_name="publish",
                    arguments={"profile_id": "profile-1"},
                )
            ]
        )


@pytest.mark.asyncio
async def test_agent_execution_persists_trajectory_and_waiting_approval(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'agent-execution.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def publish(payload: BaseModel) -> BaseModel:
        del payload
        raise AssertionError("approval-gated tool must not execute")

    publish_spec = ToolSpec(
        name="publish",
        version="v1",
        description="Publish an approved profile",
        input_schema="PublishInput",
        output_schema="PublishOutput",
        side_effect="irreversible",
        idempotency="required",
        required_permission="admin",
        requires_approval=True,
        timeout_seconds=1,
        estimated_cost=Decimal("0.2"),
    )
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            spec=publish_spec,
            input_model=PublishInput,
            output_model=PublishOutput,
            handler=publish,
        )
    )
    runtime = StructuredCallAgentRuntime(
        model=ApprovalModel(),
        tools=registry,
        output_schemas={"ReviewOutput": ReviewOutput},
        settings=Settings(
            agent_max_turns_default=3,
            agent_max_tool_calls_default=3,
            agent_max_cost_default=Decimal("1"),
            agent_deadline_seconds_default=30,
        ),
    )
    spec = AgentSpec(
        agent_id="review-agent",
        version="v1",
        objective="Review and publish",
        model_policy="reasoning-medium",
        prompt_version="prompt-v1",
        allowed_tools=["publish"],
        output_schema="ReviewOutput",
        max_turns=3,
        max_tool_calls=3,
        max_cost=Decimal("1"),
        deadline_seconds=30,
        approval_policy="write_requires_approval",
    )
    context = AgentContextPacket(
        objective="Review and publish",
        available_tool_names=["publish"],
        token_budget=1_000,
        context_hash="c" * 64,
    )

    async with sessions() as session:
        ingestion = IngestionService(session, LocalArtifactStore(tmp_path / "artifacts"))
        novel = await ingestion.upload(filename="agent.txt", data="第一章".encode())
        run = await ingestion.create_run(novel.id, "agent-execution")
        assert run is not None
        step = await session.scalar(
            select(PipelineStepORM).where(PipelineStepORM.run_id == run.id)
        )
        assert step is not None
        step.status = "running"
        step.lease_generation = 2
        step.lease_owner = "worker-1"
        step.lease_expires_at = datetime.now(UTC)
        run.status = "running"
        await session.commit()

        execution = await AgentExecutionService(session).execute(
            pipeline_step_id=step.id,
            expected_generation=2,
            runtime=runtime,
            spec=spec,
            context=context,
            permission=ToolPermission.ADMIN,
            tool_specs={"publish": publish_spec},
            evaluation_version="eval-v1",
        )
        assert execution.result.status == "approval_required"
        assert execution.created_approval is not None
        assert len(execution.created_approval.recovery_token) >= 16

    async with sessions() as session:
        agent_run = await session.get(AgentRunORM, execution.agent_run_id)
        step = await session.get(PipelineStepORM, step.id)
        turn = await session.scalar(
            select(AgentTurnORM).where(AgentTurnORM.agent_run_id == execution.agent_run_id)
        )
        tool_call = await session.scalar(
            select(ToolCallORM).where(ToolCallORM.agent_run_id == execution.agent_run_id)
        )
        approval = await session.scalar(
            select(HumanApprovalORM).where(
                HumanApprovalORM.requested_by_agent_run_id == execution.agent_run_id
            )
        )
        assert agent_run is not None and agent_run.status == "waiting_approval"
        assert agent_run.agent_spec_snapshot["prompt_version"] == "prompt-v1"
        assert turn is not None and turn.output_summary["tool_call_count"] == 1
        assert tool_call is not None and tool_call.status == "approval_required"
        assert approval is not None and approval.status == "pending"
        assert step is not None and step.status == "waiting_approval"
        assert step.lease_owner is None

    await engine.dispose()
