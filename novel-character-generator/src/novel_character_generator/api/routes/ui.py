from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/")
async def ui_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui", status_code=302)


@router.get("/ui")
async def ui_shell() -> FileResponse:
    return FileResponse(
        WEB_ROOT / "index.html",
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )
