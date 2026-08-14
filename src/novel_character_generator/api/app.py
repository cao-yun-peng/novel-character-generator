from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.api.deps import get_session
from novel_character_generator.api.schemas import (
    CharacterResponse,
    NovelCreate,
    NovelResponse,
    RunResponse,
)
from novel_character_generator.application.services import NovelService
from novel_character_generator.infrastructure.db.session import create_engine, create_session_factory
from novel_character_generator.settings import get_settings

settings = get_settings()
engine = create_engine(settings)
session_factory = create_session_factory(engine)
service = NovelService()
app = FastAPI(title=settings.app_name, version="0.1.0")
SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.exec_driver_sql("SELECT 1")
    return {"status": "ready"}


@app.post("/api/v1/novels", response_model=NovelResponse, status_code=status.HTTP_201_CREATED)
async def create_novel(body: NovelCreate, session: SessionDep) -> NovelResponse:
    novel = await service.import_novel(session, body.title, body.text)
    return NovelResponse.model_validate(novel, from_attributes=True)


@app.post(
    "/api/v1/novels/{novel_id}/runs",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_extraction(
    novel_id: UUID, session: SessionDep, idempotency_key: IdempotencyKey = None
) -> RunResponse:
    try:
        run = await service.submit_extraction(
            session, novel_id, idempotency_key or f"extract:{novel_id}:{uuid4()}"
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunResponse.model_validate(run, from_attributes=True)


@app.post(
    "/api/v1/characters/{character_id}/image-runs",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_image(
    character_id: UUID,
    novel_id: UUID,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> RunResponse:
    run = await service.submit_image(
        session,
        novel_id,
        character_id,
        idempotency_key or f"image:{character_id}:{uuid4()}",
    )
    return RunResponse.model_validate(run, from_attributes=True)


@app.get("/api/v1/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: UUID, session: SessionDep) -> RunResponse:
    run = await service.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return RunResponse.model_validate(run, from_attributes=True)


@app.post("/api/v1/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(run_id: UUID, session: SessionDep) -> Response:
    run = await service.cancel(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return Response(status_code=status.HTTP_202_ACCEPTED)


@app.get("/api/v1/novels/{novel_id}/characters", response_model=list[CharacterResponse])
async def list_characters(novel_id: UUID, session: SessionDep) -> list[CharacterResponse]:
    rows = await service.list_characters(session, novel_id)
    return [CharacterResponse.model_validate(row, from_attributes=True) for row in rows]


def run() -> None:
    import uvicorn

    uvicorn.run("novel_character_generator.api.app:app", host="127.0.0.1", port=8000)
