from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.auth import require_user_api_key
from novel_character_generator.api.deps import get_session
from novel_character_generator.infrastructure.db.orm import (
    CharacterORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    MentionSpanORM,
    TextChunkORM,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["characters"],
    dependencies=[Depends(require_user_api_key)],
)


class CharacterResponse(BaseModel):
    id: UUID
    canonical_name: str
    status: str


class MentionResponse(BaseModel):
    text: str
    kind: str
    grounding_status: str
    char_start: int
    char_end: int


class ObservationResponse(BaseModel):
    id: UUID
    field_path: str
    value: Any
    evidence_quote: str | None
    grounding_status: str
    confidence: float


class ExpressionResponse(BaseModel):
    id: UUID
    outward_emotion: str
    expression_text: str | None
    evidence_quote: str
    confidence: float


@router.get("/novels/{novel_id}/characters", response_model=list[CharacterResponse])
async def list_characters(
    novel_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[CharacterResponse]:
    result = await session.scalars(
        select(CharacterORM)
        .where(CharacterORM.novel_id == novel_id)
        .order_by(CharacterORM.canonical_name)
    )
    return [
        CharacterResponse(id=item.id, canonical_name=item.canonical_name, status=item.status)
        for item in result
    ]


async def _character_or_404(session: AsyncSession, character_id: UUID) -> CharacterORM:
    character = await session.get(CharacterORM, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character_not_found")
    return character


@router.get("/characters/{character_id}/mentions", response_model=list[MentionResponse])
async def list_mentions(
    character_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[MentionResponse]:
    await _character_or_404(session, character_id)
    result = await session.scalars(
        select(MentionSpanORM)
        .join(TextChunkORM, MentionSpanORM.source_chunk_id == TextChunkORM.id)
        .where(MentionSpanORM.resolved_character_id == character_id)
        .order_by(TextChunkORM.ordinal, MentionSpanORM.char_start)
    )
    return [
        MentionResponse(
            text=item.mention_text,
            kind=item.mention_kind,
            grounding_status=item.grounding_status,
            char_start=item.char_start,
            char_end=item.char_end,
        )
        for item in result
    ]


@router.get("/characters/{character_id}/observations", response_model=list[ObservationResponse])
async def list_observations(
    character_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[ObservationResponse]:
    await _character_or_404(session, character_id)
    result = await session.scalars(
        select(FeatureObservationORM)
        .where(FeatureObservationORM.character_id == character_id)
        .order_by(FeatureObservationORM.created_at)
    )
    return [
        ObservationResponse(
            id=item.id,
            field_path=item.field_path,
            value=item.value,
            evidence_quote=item.evidence_quote,
            grounding_status=item.grounding_status,
            confidence=item.confidence,
        )
        for item in result
    ]


@router.get("/characters/{character_id}/expressions", response_model=list[ExpressionResponse])
async def list_expressions(
    character_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[ExpressionResponse]:
    await _character_or_404(session, character_id)
    result = await session.scalars(
        select(ExpressionObservationORM)
        .where(ExpressionObservationORM.character_id == character_id)
        .order_by(ExpressionObservationORM.created_at)
    )
    return [
        ExpressionResponse(
            id=item.id,
            outward_emotion=item.outward_emotion,
            expression_text=item.expression_text,
            evidence_quote=item.evidence_quote,
            confidence=item.confidence,
        )
        for item in result
    ]
