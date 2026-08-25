from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.auth import require_admin_api_key, require_user_api_key
from novel_character_generator.api.deps import get_session
from novel_character_generator.application.services.visual_enrichment_service import (
    VisualEnrichmentService,
)
from novel_character_generator.infrastructure.db.orm import (
    FeatureObservationORM,
    FeatureSuggestionORM,
    PipelineRunORM,
    PipelineStepORM,
    RetrievalPassageORM,
    RetrievalQueryHitORM,
    RetrievalQueryRunORM,
    VisualEnrichmentRejectionORM,
)
from novel_character_generator.settings import get_settings

router = APIRouter(
    prefix="/api/v1",
    tags=["visual-enrichment"],
    dependencies=[Depends(require_user_api_key)],
)


class CreateVisualEnrichmentRunRequest(BaseModel):
    field_groups: list[str] = Field(default_factory=list, max_length=7)
    life_phase_key: str | None = Field(default=None, max_length=100)
    max_provider_calls: int | None = Field(default=None, ge=1, le=8)
    context_budget_tokens: int | None = Field(default=None, ge=256, le=64_000)
    auto_plan: bool = True


class VisualEnrichmentRunResponse(BaseModel):
    id: UUID
    novel_id: UUID
    run_type: str
    status: str
    character_id: UUID
    field_groups: list[str]
    life_phase_key: str | None
    created_at: datetime
    updated_at: datetime


class VisualFieldGroupGapResponse(BaseModel):
    field_group: str
    covered: bool
    priority: str
    observed_field_paths: list[str]


class VisualFieldGapPlanResponse(BaseModel):
    character_id: UUID
    source_document_version_id: UUID
    retrieval_index_build_id: UUID | None
    retrieval_index_status: str
    life_phase_key: str | None
    available_life_phases: list[dict[str, str]]
    groups: list[VisualFieldGroupGapResponse]
    recommended_field_groups: list[str]
    policy_version: str


class RetrievalHitResponse(BaseModel):
    retrieval_passage_id: UUID
    source_channels: list[str]
    bm25_score: float | None
    vector_score: float | None
    rrf_score: float
    expansion_reason: str | None
    final_rank: int
    selected: bool


class EvidencePassageResponse(BaseModel):
    id: UUID
    chapter_ordinal: int
    ordinal: int
    content: str
    previous_passage_id: UUID | None
    next_passage_id: UUID | None


class EvidenceObservationResponse(BaseModel):
    id: UUID
    field_path: str
    value: Any
    retrieval_passage_id: UUID | None
    evidence_quote: str | None
    grounding_status: str


class EvidenceSuggestionResponse(BaseModel):
    id: UUID
    field_path: str
    value: Any
    confidence: float
    rationale: str
    status: str
    evidence_links: list[dict[str, Any]] | None


class EvidenceRejectionResponse(BaseModel):
    id: UUID
    retrieval_passage_id: UUID | None
    field_path: str
    value: Any
    evidence_quote: str
    requested_start: int
    requested_end: int
    repaired_start: int | None
    repaired_end: int | None
    reason_codes: list[str]


class VisualEnrichmentEvidenceResponse(BaseModel):
    run_id: UUID
    character_id: UUID
    query_plan_hash: str
    query_plan: dict[str, Any]
    hits: list[RetrievalHitResponse]
    passages: list[EvidencePassageResponse]
    observations: list[EvidenceObservationResponse]
    suggestions: list[EvidenceSuggestionResponse]
    rejections: list[EvidenceRejectionResponse]


class ResolveFeatureSuggestionRequest(BaseModel):
    decision: Literal["accept", "reject"]


class FeatureSuggestionResponse(BaseModel):
    id: UUID
    character_id: UUID
    field_path: str
    value: JsonValue
    suggestion_kind: str
    confidence: float
    rationale: str
    status: str
    approval_id: UUID | None
    evidence_links: list[dict[str, Any]] | None
    updated_at: datetime


def _run_response(
    run: PipelineRunORM,
    query_run: RetrievalQueryRunORM | None,
    character_id: UUID,
    *,
    field_groups: list[str] | None = None,
    life_phase_key: str | None = None,
) -> VisualEnrichmentRunResponse:
    return VisualEnrichmentRunResponse(
        id=run.id,
        novel_id=run.novel_id,
        run_type=run.run_type,
        status=run.status,
        character_id=character_id,
        field_groups=query_run.field_groups if query_run else (field_groups or []),
        life_phase_key=query_run.life_phase_key if query_run else life_phase_key,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get(
    "/characters/{character_id}/visual-field-gaps",
    response_model=VisualFieldGapPlanResponse,
)
async def get_visual_field_gaps(
    character_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    life_phase_key: str | None = None,
) -> VisualFieldGapPlanResponse:
    try:
        plan = await VisualEnrichmentService(session).field_gap_plan(
            character_id=character_id, life_phase_key=life_phase_key
        )
    except ValueError as error:
        code = str(error)
        raise HTTPException(
            status_code=404 if code.endswith("_not_found") else 422, detail=code
        ) from error
    return VisualFieldGapPlanResponse.model_validate(plan, from_attributes=True)


@router.post(
    "/characters/{character_id}/visual-enrichment-runs",
    response_model=VisualEnrichmentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_visual_enrichment_run(
    character_id: UUID,
    request: CreateVisualEnrichmentRunRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ],
) -> VisualEnrichmentRunResponse:
    settings = get_settings()
    try:
        run = await VisualEnrichmentService(session).create_run(
            character_id=character_id,
            field_groups=request.field_groups,
            life_phase_key=request.life_phase_key,
            max_provider_calls=(
                request.max_provider_calls or settings.visual_enrichment_max_provider_calls
            ),
            context_budget_tokens=(
                request.context_budget_tokens
                or settings.visual_enrichment_context_budget_tokens
            ),
            idempotency_key=idempotency_key,
            auto_plan=request.auto_plan,
        )
    except ValueError as error:
        code = str(error)
        raise HTTPException(
            status_code=404 if code.endswith("_not_found") else 422, detail=code
        ) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    step = await session.scalar(
        select(PipelineStepORM).where(
            PipelineStepORM.run_id == run.id,
            PipelineStepORM.step_key == "plan_visual_retrieval",
        )
    )
    cursor = step.cursor if step and step.cursor else {}
    raw_groups = cursor.get("field_groups")
    planned_groups = (
        [str(item) for item in raw_groups] if isinstance(raw_groups, list) else request.field_groups
    )
    return _run_response(
        run,
        None,
        character_id,
        field_groups=planned_groups,
        life_phase_key=(str(cursor["life_phase_key"]) if cursor.get("life_phase_key") else None),
    )


@router.get(
    "/characters/{character_id}/visual-enrichment-runs",
    response_model=list[VisualEnrichmentRunResponse],
)
async def list_visual_enrichment_runs(
    character_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[VisualEnrichmentRunResponse]:
    runs = list(
        await session.scalars(
            select(PipelineRunORM)
            .where(PipelineRunORM.run_type == "visual_enrichment")
            .order_by(PipelineRunORM.created_at.desc())
        )
    )
    responses: list[VisualEnrichmentRunResponse] = []
    for run in runs:
        query_run = await session.scalar(
            select(RetrievalQueryRunORM).where(
                RetrievalQueryRunORM.enrichment_run_id == run.id
            )
        )
        if query_run is not None:
            if query_run.character_id == character_id:
                responses.append(_run_response(run, query_run, character_id))
            continue
        step = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == run.id,
                PipelineStepORM.step_key == "plan_visual_retrieval",
            )
        )
        cursor = step.cursor if step and step.cursor else {}
        if cursor.get("character_id") != str(character_id):
            continue
        raw_groups = cursor.get("field_groups")
        groups = [str(item) for item in raw_groups] if isinstance(raw_groups, list) else []
        phase = cursor.get("life_phase_key")
        responses.append(
            _run_response(
                run,
                None,
                character_id,
                field_groups=groups,
                life_phase_key=str(phase) if phase else None,
            )
        )
    return responses


@router.get(
    "/visual-enrichment-runs/{run_id}/evidence",
    response_model=VisualEnrichmentEvidenceResponse,
)
async def get_visual_enrichment_evidence(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VisualEnrichmentEvidenceResponse:
    run = await session.get(PipelineRunORM, run_id)
    query_run = await session.scalar(
        select(RetrievalQueryRunORM).where(
            RetrievalQueryRunORM.enrichment_run_id == run_id
        )
    )
    if run is None or run.run_type != "visual_enrichment" or query_run is None:
        raise HTTPException(status_code=404, detail="visual_enrichment_run_not_found")
    hits = list(
        await session.scalars(
            select(RetrievalQueryHitORM)
            .where(RetrievalQueryHitORM.retrieval_query_run_id == query_run.id)
            .order_by(RetrievalQueryHitORM.final_rank)
        )
    )
    passage_ids = [hit.retrieval_passage_id for hit in hits if hit.selected]
    passages = (
        list(
            await session.scalars(
                select(RetrievalPassageORM)
                .where(RetrievalPassageORM.id.in_(passage_ids))
                .order_by(RetrievalPassageORM.ordinal)
            )
        )
        if passage_ids
        else []
    )
    observations = list(
        await session.scalars(
            select(FeatureObservationORM)
            .where(FeatureObservationORM.extraction_run_id == run.id)
            .order_by(FeatureObservationORM.created_at)
        )
    )
    suggestions = list(
        await session.scalars(
            select(FeatureSuggestionORM)
            .where(FeatureSuggestionORM.enrichment_run_id == run.id)
            .order_by(FeatureSuggestionORM.created_at)
        )
    )
    rejections = list(
        await session.scalars(
            select(VisualEnrichmentRejectionORM)
            .where(VisualEnrichmentRejectionORM.enrichment_run_id == run.id)
            .order_by(VisualEnrichmentRejectionORM.created_at)
        )
    )
    return VisualEnrichmentEvidenceResponse(
        run_id=run.id,
        character_id=query_run.character_id,
        query_plan_hash=query_run.query_plan_hash,
        query_plan=query_run.query_plan,
        hits=[RetrievalHitResponse.model_validate(item, from_attributes=True) for item in hits],
        passages=[
            EvidencePassageResponse.model_validate(item, from_attributes=True)
            for item in passages
        ],
        observations=[
            EvidenceObservationResponse.model_validate(item, from_attributes=True)
            for item in observations
        ],
        suggestions=[
            EvidenceSuggestionResponse.model_validate(item, from_attributes=True)
            for item in suggestions
        ],
        rejections=[
            EvidenceRejectionResponse.model_validate(item, from_attributes=True)
            for item in rejections
        ],
    )


@router.post(
    "/feature-suggestions/{suggestion_id}/resolve",
    response_model=FeatureSuggestionResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def resolve_feature_suggestion(
    suggestion_id: UUID,
    request: ResolveFeatureSuggestionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor_id: Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=255)],
) -> FeatureSuggestionResponse:
    try:
        suggestion = await VisualEnrichmentService(session).resolve_suggestion(
            suggestion_id=suggestion_id,
            decision=request.decision,
            actor_id=actor_id,
        )
    except ValueError as error:
        code = str(error)
        raise HTTPException(
            status_code=404 if code.endswith("_not_found") else 422, detail=code
        ) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return FeatureSuggestionResponse.model_validate(suggestion, from_attributes=True)
