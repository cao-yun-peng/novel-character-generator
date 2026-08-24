from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.auth import require_admin_api_key, require_user_api_key
from novel_character_generator.api.deps import get_session
from novel_character_generator.application.services.appearance_service import (
    AppearanceResolutionError,
    AppearanceRevisionConflict,
    AppearanceService,
    RenderProfileUpdate,
    SnapshotTarget,
)
from novel_character_generator.application.services.character_entity_service import (
    CharacterEntityService,
    EntityOperationConflict,
    MergeSource,
    SplitAssignments,
    SplitTarget,
)
from novel_character_generator.infrastructure.db.orm import (
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterEntityOperationORM,
    CharacterORM,
    CharacterRenderProfileORM,
    ExpressionObservationORM,
    FeatureObservationORM,
    MentionSpanORM,
    SourceDocumentORM,
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
    revision: int
    merged_into_character_id: UUID | None


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


class AppearanceStateResponse(BaseModel):
    id: UUID
    character_id: UUID
    temporal_scope: dict[str, JsonValue]
    label: str | None
    state_kind: str
    merge_priority: int
    age_stage: str | None
    appearance: dict[str, JsonValue]
    field_sources: dict[str, list[str]]
    resolver_version: str
    aggregation_fingerprint: str | None
    created_by_run_id: UUID | None
    record_status: str
    status: str
    created_at: datetime
    updated_at: datetime


class RenderProfileResponse(BaseModel):
    id: UUID
    character_id: UUID
    version: int
    status: str
    identity_anchor: dict[str, JsonValue]
    default_appearance_state_id: UUID | None
    default_stage_key: str | None
    appearance_state_ids: list[str]
    palette: dict[str, JsonValue]
    field_sources: dict[str, list[str]]
    field_suggestions: dict[str, JsonValue]
    unresolved_conflicts: list[dict[str, JsonValue]]
    style_preset: str
    approved_by: str | None
    approved_at: datetime | None
    revision: int
    record_status: str
    input_fingerprint: str | None
    source_document_version_id: UUID | None
    aggregation_run_id: UUID | None
    aggregation_metadata: dict[str, JsonValue] | None
    created_at: datetime
    updated_at: datetime


class UpdateRenderProfileRequest(BaseModel):
    identity_anchor: dict[str, JsonValue] = Field(default_factory=dict)
    default_stage_key: str | None = Field(default=None, max_length=100)
    appearance_state_ids: list[UUID] = Field(default_factory=list)
    palette: dict[str, JsonValue] = Field(default_factory=dict)
    field_sources: dict[str, list[str]] = Field(default_factory=dict)
    field_suggestions: dict[str, JsonValue] = Field(default_factory=dict)
    style_preset: str = Field(min_length=1, max_length=100)


class CharacterConflictResponse(BaseModel):
    id: UUID
    character_id: UUID
    field_path: str
    appearance_state_ids: list[str]
    candidate_values: list[JsonValue]
    temporal_scope: dict[str, JsonValue]
    merge_priority: int
    conflict_kind: str
    status: str
    resolution: dict[str, JsonValue] | None
    resolved_by: str | None
    resolved_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


class ResolveCharacterConflictRequest(BaseModel):
    selected_value: JsonValue


class SnapshotResponse(BaseModel):
    character_id: UUID
    render_profile_id: UUID
    render_profile_version: int
    target: dict[str, JsonValue]
    appearance_state_ids: list[UUID]
    appearance: dict[str, JsonValue]
    palette: dict[str, JsonValue]
    style_preset: str
    field_sources: dict[str, list[str]]
    resolver_version: str
    snapshot_hash: str


class MergeSourceRequest(BaseModel):
    character_id: UUID
    revision: int = Field(ge=1)


class MergeCharactersRequest(BaseModel):
    target_character_id: UUID
    sources: list[MergeSourceRequest] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=2_000)


class SplitAssignmentsRequest(BaseModel):
    mention_span_ids: list[UUID] = Field(default_factory=list)
    alias_assertion_ids: list[UUID] = Field(default_factory=list)
    observation_ids: list[UUID] = Field(default_factory=list)
    expression_ids: list[UUID] = Field(default_factory=list)
    appearance_state_ids: list[UUID] = Field(default_factory=list)
    suggestion_ids: list[UUID] = Field(default_factory=list)
    event_participant_ids: list[UUID] = Field(default_factory=list)
    scene_ids: list[UUID] = Field(default_factory=list)


class SplitTargetRequest(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=255)
    reuse_source: bool = False
    assignments: SplitAssignmentsRequest = Field(default_factory=SplitAssignmentsRequest)


class SplitCharacterRequest(BaseModel):
    targets: list[SplitTargetRequest] = Field(min_length=2)
    invalidate_render_assets: bool = False
    reason: str = Field(min_length=1, max_length=2_000)


class CharacterEntityOperationResponse(BaseModel):
    id: UUID
    operation_type: str
    novel_id: UUID
    source_character_ids: list[UUID]
    target_character_ids: list[UUID]
    action: dict[str, JsonValue]
    before_snapshot: dict[str, JsonValue]
    status: str
    actor_id: str
    reason: str
    created_at: datetime
    updated_at: datetime


def _revision(if_match: str, *, allow_zero: bool = False) -> int:
    value = if_match.strip().strip('"')
    try:
        revision = int(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="invalid_if_match_revision") from error
    minimum = 0 if allow_zero else 1
    if revision < minimum:
        raise HTTPException(status_code=400, detail="invalid_if_match_revision")
    return revision


def _state_response(row: CharacterAppearanceStateORM) -> AppearanceStateResponse:
    return AppearanceStateResponse.model_validate(row, from_attributes=True)


def _profile_response(row: CharacterRenderProfileORM) -> RenderProfileResponse:
    return RenderProfileResponse.model_validate(row, from_attributes=True)


def _conflict_response(row: CharacterConflictORM) -> CharacterConflictResponse:
    return CharacterConflictResponse.model_validate(row, from_attributes=True)


def _entity_operation_response(
    row: CharacterEntityOperationORM,
) -> CharacterEntityOperationResponse:
    return CharacterEntityOperationResponse.model_validate(row, from_attributes=True)


def _service_error(error: ValueError) -> HTTPException:
    code = str(error)
    if code.endswith("_not_found"):
        return HTTPException(status_code=404, detail=code)
    return HTTPException(status_code=422, detail=code)


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
        CharacterResponse(
            id=item.id,
            canonical_name=item.canonical_name,
            status=item.status,
            revision=item.revision,
            merged_into_character_id=item.merged_into_character_id,
        )
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
        .join(
            SourceDocumentORM,
            MentionSpanORM.source_document_version_id == SourceDocumentORM.current_version_id,
        )
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
        .join(
            SourceDocumentORM,
            FeatureObservationORM.source_document_version_id
            == SourceDocumentORM.current_version_id,
        )
        .where(
            FeatureObservationORM.character_id == character_id,
            FeatureObservationORM.record_status == "active",
        )
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
        .join(
            SourceDocumentORM,
            ExpressionObservationORM.source_document_version_id
            == SourceDocumentORM.current_version_id,
        )
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


@router.get(
    "/characters/{character_id}/appearance-states",
    response_model=list[AppearanceStateResponse],
)
async def list_appearance_states(
    character_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[AppearanceStateResponse]:
    service = AppearanceService(session)
    if await service.character(character_id) is None:
        raise HTTPException(status_code=404, detail="character_not_found")
    return [_state_response(item) for item in await service.states(character_id)]


@router.get("/characters/{character_id}/conflicts", response_model=list[CharacterConflictResponse])
async def list_character_conflicts(
    character_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> list[CharacterConflictResponse]:
    service = AppearanceService(session)
    if await service.character(character_id) is None:
        raise HTTPException(status_code=404, detail="character_not_found")
    rows = await service.conflicts(character_id)
    if status is not None:
        rows = [item for item in rows if item.status == status]
    return [_conflict_response(item) for item in rows]


@router.post("/conflicts/{conflict_id}/resolve", response_model=CharacterConflictResponse)
async def resolve_character_conflict(
    conflict_id: UUID,
    request: ResolveCharacterConflictRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
    actor_id: Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=255)],
) -> CharacterConflictResponse:
    try:
        row = await AppearanceService(session).resolve_conflict(
            conflict_id,
            selected_value=request.selected_value,
            expected_revision=_revision(if_match),
            actor_id=actor_id,
        )
    except (AppearanceRevisionConflict, AppearanceResolutionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise _service_error(error) from error
    return _conflict_response(row)


@router.get(
    "/characters/{character_id}/render-profile",
    response_model=RenderProfileResponse,
)
async def get_render_profile(
    character_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> RenderProfileResponse:
    service = AppearanceService(session)
    if await service.character(character_id) is None:
        raise HTTPException(status_code=404, detail="character_not_found")
    profile = await service.latest_profile(character_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="render_profile_not_found")
    response.headers["ETag"] = f'"{profile.revision}"'
    return _profile_response(profile)


@router.put(
    "/characters/{character_id}/render-profile",
    response_model=RenderProfileResponse,
)
async def put_render_profile(
    character_id: UUID,
    request: UpdateRenderProfileRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    if_match: Annotated[str, Header(alias="If-Match")],
) -> RenderProfileResponse:
    try:
        profile = await AppearanceService(session).put_profile(
            character_id,
            request=RenderProfileUpdate(
                identity_anchor=request.identity_anchor,
                default_stage_key=request.default_stage_key,
                appearance_state_ids=request.appearance_state_ids,
                palette=request.palette,
                field_sources=request.field_sources,
                field_suggestions=request.field_suggestions,
                style_preset=request.style_preset,
            ),
            expected_revision=_revision(if_match, allow_zero=True),
        )
    except AppearanceRevisionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise _service_error(error) from error
    response.headers["ETag"] = f'"{profile.revision}"'
    return _profile_response(profile)


@router.post(
    "/characters/{character_id}/approve",
    response_model=RenderProfileResponse,
)
async def approve_character_profile(
    character_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    if_match: Annotated[str, Header(alias="If-Match")],
    actor_id: Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=255)],
) -> RenderProfileResponse:
    try:
        profile = await AppearanceService(session).approve(
            character_id,
            expected_revision=_revision(if_match),
            actor_id=actor_id,
        )
    except (AppearanceRevisionConflict, AppearanceResolutionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise _service_error(error) from error
    response.headers["ETag"] = f'"{profile.revision}"'
    return _profile_response(profile)


@router.get(
    "/characters/{character_id}/snapshot",
    response_model=SnapshotResponse,
)
async def get_character_snapshot(
    character_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    timeline_id: UUID | None = None,
    event_id: UUID | None = None,
    scene_id: UUID | None = None,
    chapter_ordinal: Annotated[int | None, Query(ge=0)] = None,
) -> SnapshotResponse:
    try:
        payload = await AppearanceService(session).snapshot(
            character_id,
            target=SnapshotTarget(
                timeline_id=timeline_id,
                event_id=event_id,
                scene_id=scene_id,
                chapter_ordinal=chapter_ordinal,
            ),
        )
    except AppearanceResolutionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise _service_error(error) from error
    return SnapshotResponse.model_validate(payload)


@router.post(
    "/characters/merge",
    response_model=CharacterEntityOperationResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def merge_characters(
    request: MergeCharactersRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    actor_id: Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=255)],
) -> CharacterEntityOperationResponse:
    try:
        operation = await CharacterEntityService(session).merge(
            target_character_id=request.target_character_id,
            expected_target_revision=_revision(if_match),
            sources=[
                MergeSource(
                    character_id=item.character_id,
                    expected_revision=item.revision,
                )
                for item in request.sources
            ],
            reason=request.reason,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
    except EntityOperationConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise _service_error(error) from error
    return _entity_operation_response(operation)


@router.post(
    "/characters/{character_id}/split",
    response_model=CharacterEntityOperationResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def split_character(
    character_id: UUID,
    request: SplitCharacterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str, Header(alias="If-Match")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    actor_id: Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=255)],
) -> CharacterEntityOperationResponse:
    try:
        operation = await CharacterEntityService(session).split(
            source_character_id=character_id,
            expected_revision=_revision(if_match),
            targets=[
                SplitTarget(
                    canonical_name=item.canonical_name,
                    reuse_source=item.reuse_source,
                    assignments=SplitAssignments(**item.assignments.model_dump()),
                )
                for item in request.targets
            ],
            invalidate_render_assets=request.invalidate_render_assets,
            reason=request.reason,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
    except EntityOperationConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise _service_error(error) from error
    return _entity_operation_response(operation)
