from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.auth import require_user_api_key
from novel_character_generator.api.deps import get_session
from novel_character_generator.application.services.story_service import (
    StoryService,
    TemporalBindingConflict,
    TemporalBindingUpdate,
)
from novel_character_generator.infrastructure.db.orm import EventParticipantORM

router = APIRouter(
    prefix="/api/v1",
    tags=["story"],
    dependencies=[Depends(require_user_api_key)],
)


class TimelineResponse(BaseModel):
    id: UUID
    novel_id: UUID
    name: str
    parent_timeline_id: UUID | None
    branch_event_id: UUID | None
    canonicality: str


class EventParticipantResponse(BaseModel):
    character_id: UUID
    role: str
    evidence_observation_ids: list[str]


class StoryEventResponse(BaseModel):
    id: UUID
    timeline_id: UUID
    name: str | None
    story_order: Decimal | None
    starts_at: datetime | None
    ends_at: datetime | None
    participants: list[EventParticipantResponse]


class SceneResponse(BaseModel):
    id: UUID
    novel_id: UUID
    timeline_id: UUID
    event_id: UUID | None
    chapter_ordinal: int
    narrative_order: int
    point_of_view_character_id: UUID | None
    label: str | None
    source_document_version_id: UUID | None
    source_chunk_id: UUID | None
    char_start: int | None
    char_end: int | None
    presentation_mode: str
    reality_status: str
    confidence: float | None
    binding_status: str
    binding_revision: int
    created_at: datetime
    updated_at: datetime


class TemporalBindingRequest(BaseModel):
    timeline_id: UUID
    event_id: UUID | None = None
    presentation_mode: Literal[
        "direct", "flashback", "flashforward", "dream", "illusion", "rumor", "hypothetical"
    ]
    reality_status: Literal["canonical", "subjective", "alleged", "counterfactual"]


def _if_match_revision(if_match: str) -> int:
    value = if_match.strip().strip('"')
    try:
        revision = int(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="invalid_if_match_revision") from error
    if revision < 1:
        raise HTTPException(status_code=400, detail="invalid_if_match_revision")
    return revision


async def _require_novel(service: StoryService, novel_id: UUID) -> None:
    if not await service.novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="novel_not_found")


@router.get("/novels/{novel_id}/timelines", response_model=list[TimelineResponse])
async def list_timelines(
    novel_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[TimelineResponse]:
    service = StoryService(session)
    await _require_novel(service, novel_id)
    return [
        TimelineResponse.model_validate(item, from_attributes=True)
        for item in await service.timelines(novel_id)
    ]


@router.get("/novels/{novel_id}/events", response_model=list[StoryEventResponse])
async def list_events(
    novel_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[StoryEventResponse]:
    service = StoryService(session)
    await _require_novel(service, novel_id)
    events = await service.events(novel_id)
    event_ids = [event.id for event in events]
    participants = list(
        await session.scalars(
            select(EventParticipantORM)
            .where(EventParticipantORM.event_id.in_(event_ids))
            .order_by(EventParticipantORM.created_at, EventParticipantORM.id)
        )
    ) if event_ids else []
    by_event: dict[UUID, list[EventParticipantResponse]] = {}
    for participant in participants:
        by_event.setdefault(participant.event_id, []).append(
            EventParticipantResponse.model_validate(participant, from_attributes=True)
        )
    return [
        StoryEventResponse(
            id=event.id,
            timeline_id=event.timeline_id,
            name=event.name,
            story_order=event.story_order,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            participants=by_event.get(event.id, []),
        )
        for event in events
    ]


@router.get("/novels/{novel_id}/scenes", response_model=list[SceneResponse])
async def list_scenes(
    novel_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[SceneResponse]:
    service = StoryService(session)
    await _require_novel(service, novel_id)
    return [
        SceneResponse.model_validate(item, from_attributes=True)
        for item in await service.scenes(novel_id)
    ]


@router.put("/scenes/{scene_id}/temporal-binding", response_model=SceneResponse)
async def update_scene_temporal_binding(
    scene_id: UUID,
    request: TemporalBindingRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
    actor_id: Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=255)],
) -> SceneResponse:
    service = StoryService(session)
    try:
        scene = await service.update_temporal_binding(
            scene_id,
            binding=TemporalBindingUpdate(
                timeline_id=request.timeline_id,
                event_id=request.event_id,
                presentation_mode=request.presentation_mode,
                reality_status=request.reality_status,
            ),
            expected_revision=_if_match_revision(if_match),
            actor_id=actor_id,
        )
    except TemporalBindingConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if scene is None:
        raise HTTPException(status_code=404, detail="scene_not_found")
    return SceneResponse.model_validate(scene, from_attributes=True)
