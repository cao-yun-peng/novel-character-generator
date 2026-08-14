from collections.abc import Awaitable, Callable, Mapping
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", uuid4()))


def _error(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(code=code, message=message, request_id=_request_id(request))
    return JSONResponse(status_code=status_code, content=payload.model_dump(), headers=headers)


async def http_exception_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, HTTPException)
    detail = error.detail
    code = detail if isinstance(detail, str) else "http_error"
    message = detail if isinstance(detail, str) else str(detail)
    return _error(
        request,
        status_code=error.status_code,
        code=code,
        message=message,
        headers=error.headers,
    )


async def validation_exception_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    return _error(
        request,
        status_code=422,
        code="validation_error",
        message="Request validation failed",
    )


async def unhandled_exception_handler(request: Request, _: Exception) -> JSONResponse:
    return _error(
        request,
        status_code=500,
        code="internal_error",
        message="Internal server error",
    )


def configure_error_handling(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
