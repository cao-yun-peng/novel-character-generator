from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.deps import get_artifact_store, get_session
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings

router = APIRouter(prefix="/api/v1/novels", tags=["novels"])


class NovelResponse(BaseModel):
    id: UUID
    title: str
    status: str


class NovelDetailsResponse(NovelResponse):
    source_sha256: str
    chapter_count: int
    chunk_count: int


class RunResponse(BaseModel):
    id: UUID
    novel_id: UUID
    status: str
    run_type: str


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


@router.post("/{novel_id}/runs", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_ingestion_run(
    novel_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    artifact_store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> RunResponse:
    try:
        run = await IngestionService(session, artifact_store).create_run(novel_id, idempotency_key)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if run is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return RunResponse(id=run.id, novel_id=run.novel_id, status=run.status, run_type=run.run_type)


@router.post(
    "/{novel_id}/extraction-runs",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_extraction_run(
    novel_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    artifact_store: Annotated[LocalArtifactStore, Depends(get_artifact_store)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> RunResponse:
    try:
        run = await IngestionService(session, artifact_store).create_extraction_run(
            novel_id, idempotency_key
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if run is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return RunResponse(id=run.id, novel_id=run.novel_id, status=run.status, run_type=run.run_type)
