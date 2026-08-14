from collections import Counter
from collections.abc import Awaitable, Callable
from threading import Lock
from time import perf_counter

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, Response


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: Counter[tuple[str, str, int]] = Counter()
        self._duration_seconds: dict[tuple[str, str], float] = {}

    def observe(self, *, method: str, route: str, status_code: int, duration: float) -> None:
        with self._lock:
            self._requests[(method, route, status_code)] += 1
            key = (method, route)
            self._duration_seconds[key] = self._duration_seconds.get(key, 0.0) + duration

    def render(self) -> str:
        lines = [
            "# HELP novel_character_generator_http_requests_total HTTP requests.",
            "# TYPE novel_character_generator_http_requests_total counter",
        ]
        with self._lock:
            request_items = sorted(self._requests.items())
            duration_items = sorted(self._duration_seconds.items())
        for (method, route, status_code), request_count in request_items:
            labels = f'method="{method}",route="{route}",status="{status_code}"'
            lines.append(
                "novel_character_generator_http_requests_total"
                f"{{{labels}}} {request_count}"
            )
        lines.extend(
            [
                "# HELP novel_character_generator_http_request_duration_seconds_total "
                "Cumulative HTTP request duration.",
                "# TYPE novel_character_generator_http_request_duration_seconds_total counter",
            ]
        )
        for (method, route), duration_total in duration_items:
            labels = f'method="{method}",route="{route}"'
            lines.append(
                "novel_character_generator_http_request_duration_seconds_total"
                f"{{{labels}}} {duration_total:.9f}"
            )
        return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = perf_counter()
        response = await call_next(request)
        route_object = request.scope.get("route")
        route = getattr(route_object, "path", "unmatched")
        metrics_registry.observe(
            method=request.method,
            route=route,
            status_code=response.status_code,
            duration=perf_counter() - started,
        )
        return response


async def metrics() -> PlainTextResponse:
    return PlainTextResponse(
        metrics_registry.render(), media_type="text/plain; version=0.0.4; charset=utf-8"
    )
