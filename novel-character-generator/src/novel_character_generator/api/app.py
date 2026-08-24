from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from novel_character_generator.api.auth import require_admin_api_key, require_user_api_key
from novel_character_generator.api.errors import configure_error_handling
from novel_character_generator.api.metrics import MetricsMiddleware, metrics
from novel_character_generator.api.routes import (
    agent_runs,
    approvals,
    capabilities,
    characters,
    health,
    novels,
    runs,
    story,
    ui,
)
from novel_character_generator.infrastructure.db.session import dispose_engine
from novel_character_generator.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="Novel Character Generator", version="0.1.0", lifespan=lifespan)
    configure_error_handling(app)
    app.mount("/ui/assets", StaticFiles(directory=ui.WEB_ROOT), name="ui-assets")
    if get_settings().metrics_enabled:
        app.add_middleware(MetricsMiddleware)
        app.add_api_route(
            get_settings().metrics_path,
            metrics,
            methods=["GET"],
            dependencies=[Depends(require_admin_api_key)],
            include_in_schema=False,
        )
    app.include_router(health.router)
    app.include_router(capabilities.router, dependencies=[Depends(require_user_api_key)])
    app.include_router(novels.router)
    app.include_router(characters.router)
    app.include_router(runs.router)
    app.include_router(approvals.router)
    app.include_router(agent_runs.router)
    app.include_router(story.router)
    app.include_router(ui.router)
    return app


app = create_app()
