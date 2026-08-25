from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.auth import require_user_api_key
from novel_character_generator.api.deps import get_artifact_store, get_session
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings

router = APIRouter(
    prefix="/api/v1/novels",
    tags=["novels"],
    dependencies=[Depends(require_user_api_key)],
)


class NovelResponse(BaseModel):
    id: UUID
    title: str
    status: str


class NovelDetailsResponse(NovelResponse):
    source_sha256: str
    chapter_count: int
    chunk_count: int
    retrieval_index_build_id: UUID | None
    retrieval_index_status: str | None
    retrieval_passage_count: int


class NovelHistoryResponse(NovelResponse):
    created_at: datetime
    updated_at: datetime


class RunResponse(BaseModel):
    id: UUID
    novel_id: UUID
    status: str
    run_type: str


class RunHistoryResponse(RunResponse):
    created_at: datetime
    updated_at: datetime


class RetrievalIndexRunResponse(BaseModel):
    run_id: UUID
    run_status: str
    retrieval_index_build_id: UUID
    retrieval_index_status: str


class DocumentVersionResponse(BaseModel):
    id: UUID
    source_document_id: UUID
    version: int
    content_sha256: str


@router.get("", response_model=list[NovelHistoryResponse])
async def list_novels(
    session: Annotated[AsyncSession, Depends(get_session)],
    artifact_store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[NovelHistoryResponse]:
    novels = await IngestionService(session, artifact_store).list_novels(limit=limit)
    return [NovelHistoryResponse.model_validate(item, from_attributes=True) for item in novels]


@router.post("", response_model=NovelResponse, status_code=status.HTTP_201_CREATED)
async def upload_novel(
    file: Annotated[UploadFile, File()],
    session: Annotated[AsyncSession, Depends(get_session)],
    artifact_store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> NovelResponse:
    if file.content_type not in {None, "text/plain", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="unsupported_file_type")
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=415, detail="txt_file_required")
    data = await file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")
    try:
        novel = await IngestionService(session, artifact_store).upload(
            filename=file.filename, data=data
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return NovelResponse(id=novel.id, title=novel.title, status=novel.status)


@router.get("/{novel_id}", response_model=NovelDetailsResponse)
async def get_novel(
    novel_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    artifact_store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> NovelDetailsResponse:
    details = await IngestionService(session, artifact_store).details(novel_id)
    if details is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return NovelDetailsResponse(**details.__dict__)


@router.post(
    "/{novel_id}/versions",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_novel_version(
    novel_id: UUID,
    file: Annotated[UploadFile, File()],
    session: Annotated[AsyncSession, Depends(get_session)],
    artifact_store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> DocumentVersionResponse:
    if file.content_type not in {None, "text/plain", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="unsupported_file_type")
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=415, detail="txt_file_required")
    data = await file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")
    try:
        document_version = await IngestionService(session, artifact_store).upload_version(
            novel_id=novel_id,
            filename=file.filename,
            data=data,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if document_version is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return DocumentVersionResponse(
        id=document_version.id,
        source_document_id=document_version.source_document_id,
        version=document_version.version,
        content_sha256=document_version.content_sha256,
    )


@router.post("/{novel_id}/runs", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_text_analysis_run(
    novel_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    artifact_store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> RunResponse:
    try:
        run = await IngestionService(session, artifact_store).create_analysis_run(
            novel_id, idempotency_key
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if run is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return RunResponse(id=run.id, novel_id=run.novel_id, status=run.status, run_type=run.run_type)


@router.post(
    "/{novel_id}/retrieval-index-runs",
    response_model=RetrievalIndexRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ensure_retrieval_index_run(
    novel_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    artifact_store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
) -> RetrievalIndexRunResponse:
    try:
        result = await IngestionService(session, artifact_store).ensure_retrieval_index(novel_id)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    build, run = result
    return RetrievalIndexRunResponse(
        run_id=run.id,
        run_status=run.status,
        retrieval_index_build_id=build.id,
        retrieval_index_status=build.status,
    )


@router.get("/{novel_id}/runs", response_model=list[RunHistoryResponse])
async def list_novel_runs(
    novel_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    artifact_store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RunHistoryResponse]:
    runs = await IngestionService(session, artifact_store).list_runs(novel_id, limit=limit)
    if runs is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return [RunHistoryResponse.model_validate(item, from_attributes=True) for item in runs]


