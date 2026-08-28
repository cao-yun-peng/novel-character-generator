from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.auth import require_user_api_key
from novel_character_generator.api.deps import get_session
from novel_character_generator.application.services.appearance_service import (
    AppearanceResolutionError,
)
from novel_character_generator.application.services.generation_context_service import (
    ImageRunRequest,
    ImageRunService,
)
from novel_character_generator.infrastructure.db.orm import (
    ArtifactORM,
    GeneratedImageORM,
    GenerationContextORM,
    PipelineRunORM,
)
from novel_character_generator.settings import get_settings

router = APIRouter(
    prefix="/api/v1",
    tags=["image-generation"],
    dependencies=[Depends(require_user_api_key)],
)


class CreateImageRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeline_id: UUID
    target_event_id: UUID | None = None
    target_scene_id: UUID | None = None
    target_chapter_ordinal: int | None = Field(default=None, ge=0)
    stage_keys: list[str] = Field(default_factory=list, max_length=1)
    candidate_count: int = Field(default=1, ge=1, le=8)
    generate_character_sheet: bool = False
    generation_mode: Literal["concept", "character_design", "consistent_scene"] = "concept"
    render_overrides: dict[str, Any] = Field(default_factory=dict)
    budget_limit: Decimal = Field(default=Decimal("0"), ge=0)


class ImageRunCreatedResponse(BaseModel):
    run_id: UUID
    character_id: UUID
    status: str
    generation_context_ids: list[UUID]
    estimated_cost: Decimal


class GeneratedImageResponse(BaseModel):
    id: UUID
    artifact_id: UUID
    content_hash: str
    mime_type: str
    byte_size: int
    workflow_profile: str
    workflow_version: str
    snapshot_hash: str
    evaluation: dict[str, Any] | None


class ImageRunDetailsResponse(BaseModel):
    run_id: UUID
    character_id: UUID | None
    status: str
    context_hash: str | None
    context_status: str | None
    generation_mode: str | None
    scene_brief_hash: str | None
    render_spec_hash: str | None
    render_readiness: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    images: list[GeneratedImageResponse]


def _service(session: AsyncSession) -> ImageRunService:
    settings = get_settings()
    if settings.image_provider == "disabled":
        raise HTTPException(status_code=503, detail="image_generation_disabled")
    return ImageRunService(
        session,
        provider=settings.image_provider,
        workflow_profile=settings.image_workflow_profile,
        workflow_version=settings.image_workflow_version,
        candidate_count_max=settings.image_candidate_count_max,
    )


@router.post(
    "/characters/{character_id}/image-runs",
    response_model=ImageRunCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_image_run(
    character_id: UUID,
    request: CreateImageRunRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ],
) -> ImageRunCreatedResponse:
    try:
        run = await _service(session).create_run(
            character_id=character_id,
            request=ImageRunRequest(
                timeline_id=request.timeline_id,
                target_event_id=request.target_event_id,
                target_scene_id=request.target_scene_id,
                target_chapter_ordinal=request.target_chapter_ordinal,
                stage_keys=request.stage_keys,
                candidate_count=request.candidate_count,
                generate_character_sheet=request.generate_character_sheet,
                generation_mode=request.generation_mode,
                render_overrides=request.render_overrides,
                budget_limit=request.budget_limit,
            ),
            idempotency_key=idempotency_key,
        )
    except ValueError as error:
        code = str(error)
        raise HTTPException(
            status_code=404 if code.endswith("_not_found") else 422,
            detail=code,
        ) from error
    except (AppearanceResolutionError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    context_ids = list(
        await session.scalars(
            select(GenerationContextORM.id).where(GenerationContextORM.run_id == run.id)
        )
    )
    return ImageRunCreatedResponse(
        run_id=run.id,
        character_id=character_id,
        status=run.status,
        generation_context_ids=context_ids,
        estimated_cost=Decimal("0"),
    )


@router.get("/image-runs/{run_id}", response_model=ImageRunDetailsResponse)
async def get_image_run(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ImageRunDetailsResponse:
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type != "image_generation":
        raise HTTPException(status_code=404, detail="image_generation_run_not_found")
    context = await session.scalar(
        select(GenerationContextORM).where(GenerationContextORM.run_id == run.id)
    )
    rows = list(
        await session.execute(
            select(GeneratedImageORM, ArtifactORM)
            .join(ArtifactORM, ArtifactORM.id == GeneratedImageORM.artifact_id)
            .where(GeneratedImageORM.run_id == run.id)
            .order_by(GeneratedImageORM.created_at)
        )
    )
    return ImageRunDetailsResponse(
        run_id=run.id,
        character_id=context.character_id if context else None,
        status=run.status,
        context_hash=context.context_hash if context else None,
        context_status=context.status if context else None,
        generation_mode=(
            str(context.context_payload.get("generation_mode")) if context else None
        ),
        scene_brief_hash=(
            str(context.context_payload.get("scene_render_brief", {}).get("brief_hash"))
            if context
            and isinstance(context.context_payload.get("scene_render_brief"), dict)
            else None
        ),
        render_spec_hash=(
            str(context.context_payload.get("image_render_spec", {}).get("spec_hash"))
            if context
            and isinstance(context.context_payload.get("image_render_spec"), dict)
            else None
        ),
        render_readiness=(
            dict(context.context_payload.get("render_readiness", {})) if context else None
        ),
        created_at=run.created_at,
        updated_at=run.updated_at,
        images=[
            GeneratedImageResponse(
                id=image.id,
                artifact_id=artifact.id,
                content_hash=artifact.content_hash,
                mime_type=artifact.mime_type,
                byte_size=artifact.byte_size,
                workflow_profile=image.workflow_profile,
                workflow_version=image.workflow_version,
                snapshot_hash=image.snapshot_hash,
                evaluation=image.evaluation,
            )
            for image, artifact in rows
        ],
    )


@router.get(
    "/characters/{character_id}/image-runs",
    response_model=list[ImageRunDetailsResponse],
)
async def list_image_runs(
    character_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ImageRunDetailsResponse]:
    run_ids = list(
        await session.scalars(
            select(GenerationContextORM.run_id)
            .where(GenerationContextORM.character_id == character_id)
            .order_by(GenerationContextORM.created_at.desc())
            .limit(limit)
        )
    )
    return [await get_image_run(run_id, session) for run_id in run_ids]
