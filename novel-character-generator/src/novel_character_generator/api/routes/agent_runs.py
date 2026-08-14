from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.auth import require_user_api_key
from novel_character_generator.api.deps import get_session
from novel_character_generator.infrastructure.db.orm import (
    AgentRunORM,
    AgentTurnORM,
    DecisionRecordORM,
    ToolCallORM,
)

router = APIRouter(
    prefix="/api/v1/agent-runs",
    tags=["agent-runs"],
    dependencies=[Depends(require_user_api_key)],
)


class AgentRunSummaryResponse(BaseModel):
    id: UUID
    pipeline_step_id: UUID
    agent_id: str
    agent_version: str
    status: str
    attempt: int
    prompt_version: str
    model_policy: str
    output_schema: str
    permission: str
    budget: dict[str, Any]
    context_hash: str
    final_output_hash: str | None
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    total_cost: Decimal
    latency_ms: int
    started_at: datetime | None
    completed_at: datetime | None


class AgentTurnResponse(BaseModel):
    id: UUID
    turn_number: int
    input_context_hash: str
    output_summary: dict[str, Any]
    usage: dict[str, Any]
    created_at: datetime


class ToolCallResponse(BaseModel):
    id: UUID
    call_id: str
    tool_name: str
    tool_version: str
    input_hash: str
    output_hash: str | None
    status: str
    side_effect: bool
    duration_ms: int
    error_code: str | None
    created_at: datetime


class AgentRunDetailsResponse(AgentRunSummaryResponse):
    agent_spec_snapshot: dict[str, Any]
    tool_spec_versions: dict[str, str]
    evaluation_version: str | None
    turns: list[AgentTurnResponse]
    tool_calls: list[ToolCallResponse]
    decision_record_ids: list[UUID]


def agent_run_summary(row: AgentRunORM) -> AgentRunSummaryResponse:
    return AgentRunSummaryResponse.model_validate(row, from_attributes=True)


@router.get("/{agent_run_id}", response_model=AgentRunDetailsResponse)
async def get_agent_run(
    agent_run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRunDetailsResponse:
    agent_run = await session.get(AgentRunORM, agent_run_id)
    if agent_run is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    turns = list(
        await session.scalars(
            select(AgentTurnORM)
            .where(AgentTurnORM.agent_run_id == agent_run_id)
            .order_by(AgentTurnORM.turn_number)
        )
    )
    tool_calls = list(
        await session.scalars(
            select(ToolCallORM)
            .where(ToolCallORM.agent_run_id == agent_run_id)
            .order_by(ToolCallORM.created_at, ToolCallORM.id)
        )
    )
    decision_ids = list(
        await session.scalars(
            select(DecisionRecordORM.id)
            .where(DecisionRecordORM.agent_run_id == agent_run_id)
            .order_by(DecisionRecordORM.created_at, DecisionRecordORM.id)
        )
    )
    summary = agent_run_summary(agent_run).model_dump()
    return AgentRunDetailsResponse(
        **summary,
        agent_spec_snapshot=agent_run.agent_spec_snapshot,
        tool_spec_versions=agent_run.tool_spec_versions,
        evaluation_version=agent_run.evaluation_version,
        turns=[AgentTurnResponse.model_validate(item, from_attributes=True) for item in turns],
        tool_calls=[
            ToolCallResponse.model_validate(item, from_attributes=True) for item in tool_calls
        ],
        decision_record_ids=decision_ids,
    )
