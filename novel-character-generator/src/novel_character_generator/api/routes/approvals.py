from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.auth import require_admin_api_key
from novel_character_generator.api.deps import get_session
from novel_character_generator.application.services.approval_service import (
    ApprovalConflict,
    ApprovalService,
)
from novel_character_generator.infrastructure.db.orm import HumanApprovalORM

router = APIRouter(
    prefix="/api/v1/approvals",
    tags=["approvals"],
    dependencies=[Depends(require_admin_api_key)],
)


class ApprovalResponse(BaseModel):
    id: UUID
    pipeline_step_id: UUID | None
    requested_by_agent_run_id: UUID | None
    approval_type: str
    subject_type: str
    subject_id: UUID
    action: dict[str, JsonValue]
    estimated_cost: dict[str, JsonValue] | None
    status: str
    decision: str | None
    modifications: dict[str, JsonValue] | None
    resolved_by: str | None
    expires_at: datetime
    resolved_at: datetime | None
    revision: int
    created_at: datetime


class ApprovalPageResponse(BaseModel):
    items: list[ApprovalResponse]
    next_cursor: UUID | None


class ResolveApprovalRequest(BaseModel):
    decision: Literal["approve", "reject", "modify", "defer"]
    modifications: dict[str, JsonValue] | None = None
    defer_until: datetime | None = None


def _response(row: HumanApprovalORM) -> ApprovalResponse:
    return ApprovalResponse.model_validate(row, from_attributes=True)


def _revision(if_match: str) -> int:
    value = if_match.strip().strip('"')
    try:
        revision = int(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="invalid_if_match_revision") from error
    if revision < 1:
        raise HTTPException(status_code=400, detail="invalid_if_match_revision")
    return revision


@router.get("", response_model=ApprovalPageResponse)
async def list_approvals(
    session: Annotated[AsyncSession, Depends(get_session)],
    status: Annotated[str | None, Query(max_length=32)] = "pending",
    approval_type: Annotated[str | None, Query(alias="type", max_length=100)] = None,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ApprovalPageResponse:
    try:
        page = await ApprovalService(session).list_pending(
            status=status,
            approval_type=approval_type,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return ApprovalPageResponse(
        items=[_response(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/{approval_id}/resolve", response_model=ApprovalResponse)
async def resolve_approval(
    approval_id: UUID,
    request: ResolveApprovalRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
    actor_id: Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=255)],
    recovery_token: Annotated[
        str | None, Header(alias="X-Recovery-Token", min_length=16)
    ] = None,
) -> ApprovalResponse:
    try:
        approval = await ApprovalService(session).resolve(
            approval_id,
            decision=request.decision,
            expected_revision=_revision(if_match),
            recovery_token=recovery_token,
            resolved_by=actor_id,
            modifications=request.modifications,
            defer_until=request.defer_until,
        )
    except ApprovalConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        if str(error) == "approval_not_found":
            raise HTTPException(status_code=404, detail=str(error)) from error
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _response(approval)
