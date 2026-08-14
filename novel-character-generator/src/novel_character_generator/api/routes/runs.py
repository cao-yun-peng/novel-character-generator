import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.auth import require_user_api_key
from novel_character_generator.api.deps import get_session
from novel_character_generator.api.routes.agent_runs import (
    AgentRunSummaryResponse,
    agent_run_summary,
)
from novel_character_generator.application.services.run_service import RunService
from novel_character_generator.infrastructure.db.orm import (
    AgentRunORM,
    PipelineRunORM,
    PipelineStepORM,
)
from novel_character_generator.infrastructure.db.repositories.external_operations import (
    ExternalOperationRepository,
)
from novel_character_generator.infrastructure.db.repositories.run_events import read_run_events
from novel_character_generator.infrastructure.db.session import session_factory
from novel_character_generator.settings import get_settings

router = APIRouter(
    prefix="/api/v1/runs",
    tags=["runs"],
    dependencies=[Depends(require_user_api_key)],
)


class StepResponse(BaseModel):
    id: UUID
    step_key: str
    status: str
    attempt: int
    cursor: dict[str, object] | None
    error_code: str | None


class RunDetailsResponse(BaseModel):
    id: UUID
    novel_id: UUID
    run_type: str
    status: str
    cancel_requested: bool
    steps: list[StepResponse]


class ExternalOperationResponse(BaseModel):
    id: UUID
    pipeline_step_id: UUID
    provider: str
    operation_kind: str
    status: str
    request_fingerprint: str
    provider_request_id: str | None
    lease_generation: int
    attempt: int


async def _run_or_404(service: RunService, run_id: UUID) -> RunDetailsResponse:
    details = await service.details(run_id)
    if details is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return RunDetailsResponse.model_validate(details, from_attributes=True)


@router.get("/{run_id}", response_model=RunDetailsResponse)
async def get_run(
    run_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> RunDetailsResponse:
    return await _run_or_404(RunService(session), run_id)


@router.get("/{run_id}/events", response_class=StreamingResponse)
async def stream_run_events(
    run_id: UUID,
    after: Annotated[int, Query(ge=0)] = 0,
    follow: bool = True,
) -> StreamingResponse:
    async with session_factory() as session:
        if await session.get(PipelineRunORM, run_id) is None:
            raise HTTPException(status_code=404, detail="run_not_found")

    async def event_stream() -> AsyncIterator[str]:
        sequence = after
        while True:
            async with session_factory() as session:
                events = await read_run_events(
                    session, run_id=run_id, after_sequence=sequence
                )
                run = await session.get(PipelineRunORM, run_id)
            for event in events:
                sequence = event.sequence
                data = json.dumps(event.payload, ensure_ascii=False, default=str)
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {data}\n\n"
            terminal = run is None or run.status in {"succeeded", "failed", "cancelled"}
            if not follow or (terminal and not events):
                return
            if not events:
                yield ": keep-alive\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/{run_id}/external-operations",
    response_model=list[ExternalOperationResponse],
)
async def list_external_operations(
    run_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[ExternalOperationResponse]:
    if await session.get(PipelineRunORM, run_id) is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    operations = await ExternalOperationRepository(session).list_for_run(run_id)
    return [
        ExternalOperationResponse.model_validate(operation, from_attributes=True)
        for operation in operations
    ]


@router.get("/{run_id}/agent-runs", response_model=list[AgentRunSummaryResponse])
async def list_agent_runs(
    run_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[AgentRunSummaryResponse]:
    if await session.get(PipelineRunORM, run_id) is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    rows = list(
        await session.scalars(
            select(AgentRunORM)
            .join(PipelineStepORM, AgentRunORM.pipeline_step_id == PipelineStepORM.id)
            .where(PipelineStepORM.run_id == run_id)
            .order_by(AgentRunORM.created_at, AgentRunORM.id)
        )
    )
    return [agent_run_summary(row) for row in rows]


@router.post(
    "/{run_id}/cancel",
    response_model=RunDetailsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_run(
    run_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> RunDetailsResponse:
    service = RunService(session)
    try:
        details = await service.request_cancel(run_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if details is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return RunDetailsResponse.model_validate(details, from_attributes=True)


@router.post(
    "/{run_id}/retry",
    response_model=RunDetailsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_run(
    run_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> RunDetailsResponse:
    service = RunService(session)
    try:
        details = await service.retry(run_id, max_attempts=get_settings().max_task_attempts)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if details is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return RunDetailsResponse.model_validate(details, from_attributes=True)
