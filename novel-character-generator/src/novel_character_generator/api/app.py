from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from novel_character_generator.api.routes import health, novels
from novel_character_generator.infrastructure.db.session import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="Novel Character Generator", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(novels.router)
    return app


app = create_app()
