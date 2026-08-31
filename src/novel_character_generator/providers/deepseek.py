from __future__ import annotations

import copy
import json
import os
import socket
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from ..errors import (
    ProviderAuthenticationError,
    ProviderBadRequestError,
    ProviderConfigurationError,
    ProviderError,
    ProviderInsufficientBalanceError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTransientError,
)
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_RESPONSES_PATH = "/responses"
RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
REASONING_EFFORTS = frozenset({"none", "low", "high", "max"})


class StructuredProviderRequest(Protocol):
    system_instruction: str
    user_payload: Mapping[str, Any]
    response_schema: Mapping[str, Any]
    response_schema_name: str


def _positive_float(value: str, *, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ProviderConfigurationError(f"{name} must be a number") from exc
    if parsed <= 0:
        raise ProviderConfigurationError(f"{name} must be greater than zero")
    return parsed


def _non_negative_float(value: str, *, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ProviderConfigurationError(f"{name} must be a number") from exc
    if parsed < 0:
        raise ProviderConfigurationError(f"{name} cannot be negative")
    return parsed


def _positive_int(value: str, *, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ProviderConfigurationError(f"{name} must be an integer") from exc
    if parsed < 1:
        raise ProviderConfigurationError(f"{name} must be a positive integer")
    return parsed


def _validate_base_url(base_url: str) -> str:
    if not isinstance(base_url, str):
        raise ProviderConfigurationError("DEEPSEEK_BASE_URL must be a string")
    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ProviderConfigurationError("DEEPSEEK_BASE_URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise ProviderConfigurationError("DEEPSEEK_BASE_URL cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise ProviderConfigurationError("DEEPSEEK_BASE_URL cannot contain query or fragment data")
    return normalized


@dataclass(frozen=True)
class DeepSeekConfig:
    """Versioned runtime controls for the DeepSeek Responses API adapter."""

    api_key: str = field(repr=False, compare=False)
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    model: str = DEFAULT_DEEPSEEK_MODEL
    timeout_seconds: float = 60.0
    max_attempts: int = 3
    max_output_tokens: int = 4096
    reasoning_effort: str = "low"
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 8.0

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ProviderConfigurationError("DEEPSEEK_API_KEY is required")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ProviderConfigurationError("DEEPSEEK_MODEL must be non-empty")
        object.__setattr__(self, "api_key", self.api_key.strip())
        object.__setattr__(self, "base_url", _validate_base_url(self.base_url))
        object.__setattr__(self, "model", self.model.strip())
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise ProviderConfigurationError("timeout_seconds must be greater than zero")
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise ProviderConfigurationError("max_attempts must be at least one")
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or self.max_output_tokens < 1
        ):
            raise ProviderConfigurationError("max_output_tokens must be at least one")
        if not isinstance(self.reasoning_effort, str) or self.reasoning_effort not in REASONING_EFFORTS:
            raise ProviderConfigurationError(
                "reasoning_effort must be one of none, low, high, max"
            )
        for value, name in (
            (self.initial_backoff_seconds, "initial_backoff_seconds"),
            (self.max_backoff_seconds, "max_backoff_seconds"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProviderConfigurationError(f"{name} must be a number")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ProviderConfigurationError("backoff values cannot be negative")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ProviderConfigurationError(
                "max_backoff_seconds cannot be smaller than initial_backoff_seconds"
            )

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}{DEEPSEEK_RESPONSES_PATH}"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DeepSeekConfig:
        values = os.environ if env is None else env
        api_key = values.get("DEEPSEEK_API_KEY", "").strip()
        return cls(
            api_key=api_key,
            base_url=values.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
            model=values.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            timeout_seconds=_positive_float(
                values.get("DEEPSEEK_TIMEOUT_SECONDS", "60"),
                name="DEEPSEEK_TIMEOUT_SECONDS",
            ),
            max_attempts=_positive_int(
                values.get("DEEPSEEK_MAX_ATTEMPTS", "3"),
                name="DEEPSEEK_MAX_ATTEMPTS",
            ),
            max_output_tokens=_positive_int(
                values.get("DEEPSEEK_MAX_OUTPUT_TOKENS", "4096"),
                name="DEEPSEEK_MAX_OUTPUT_TOKENS",
            ),
            reasoning_effort=values.get("DEEPSEEK_REASONING_EFFORT", "low").strip(),
            initial_backoff_seconds=_non_negative_float(
                values.get("DEEPSEEK_INITIAL_BACKOFF_SECONDS", "0.5"),
                name="DEEPSEEK_INITIAL_BACKOFF_SECONDS",
            ),
            max_backoff_seconds=_non_negative_float(
                values.get("DEEPSEEK_MAX_BACKOFF_SECONDS", "8"),
                name="DEEPSEEK_MAX_BACKOFF_SECONDS",
            ),
        )


@dataclass(frozen=True)
class DeepSeekHTTPResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class DeepSeekTransport(Protocol):
    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> DeepSeekHTTPResponse: ...


class UrllibDeepSeekTransport:
    """Small synchronous HTTPS transport using Python's verified default TLS context."""

    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> DeepSeekHTTPResponse:
        request = Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return DeepSeekHTTPResponse(
                    status_code=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response.read(),
                )
        except HTTPError as exc:
            return DeepSeekHTTPResponse(
                status_code=exc.code,
                headers=(
                    {key.lower(): value for key, value in exc.headers.items()}
                    if exc.headers is not None
                    else {}
                ),
                body=exc.read(),
            )


@dataclass(frozen=True)
class DeepSeekUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class DeepSeekCallTrace:
    """Prompt-free, credential-free metadata for one completed Provider call."""

    provider: str
    api: str
    model: str
    endpoint_origin: str
    attempts: int
    success: bool
    duration_ms: int
    http_status: int | None
    response_id: str | None
    usage: DeepSeekUsage
    error_kind: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "api": self.api,
            "model": self.model,
            "endpoint_origin": self.endpoint_origin,
            "attempts": self.attempts,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "http_status": self.http_status,
            "response_id": self.response_id,
            "usage": self.usage.to_dict(),
            "error_kind": self.error_kind,
        }


TraceSink = Callable[[DeepSeekCallTrace], None]
Sleeper = Callable[[float], None]
Clock = Callable[[], float]


class DeepSeekProvider:
    """M1 Provider backed by DeepSeek's stateless Responses API."""

    def __init__(
        self,
        config: DeepSeekConfig,
        *,
        transport: DeepSeekTransport | None = None,
        trace_sink: TraceSink | None = None,
        sleeper: Sleeper = time.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self.config = config
        self._transport = transport or UrllibDeepSeekTransport()
        self._trace_sink = trace_sink
        self._sleeper = sleeper
        self._clock = clock

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> DeepSeekProvider:
        return cls(DeepSeekConfig.from_env(env), **kwargs)

    def generate(self, request: StructuredProviderRequest) -> str:
        body = self._build_request_body(request)
        started_at = self._clock()
        last_status: int | None = None
        attempts = 0

        for attempt in range(1, self.config.max_attempts + 1):
            attempts = attempt
            try:
                response = self._transport.post(
                    url=self.config.endpoint,
                    headers=self._headers(),
                    body=body,
                    timeout_seconds=self.config.timeout_seconds,
                )
            except (TimeoutError, socket.timeout, URLError, OSError, HTTPException) as exc:
                if attempt < self.config.max_attempts:
                    self._sleeper(self._backoff_seconds(attempt, {}))
                    continue
                error = ProviderTransientError(
                    "DeepSeek request failed after bounded network retries",
                    retryable=True,
                )
                self._emit_trace(
                    started_at=started_at,
                    attempts=attempts,
                    success=False,
                    http_status=None,
                    response_id=None,
                    usage=DeepSeekUsage(),
                    error_kind=type(error).__name__,
                )
                raise error from exc

            last_status = response.status_code
            if 200 <= response.status_code < 300:
                try:
                    output_text, response_id, usage = self._parse_success(response.body)
                except ProviderTransientError as exc:
                    if attempt < self.config.max_attempts:
                        self._sleeper(self._backoff_seconds(attempt, response.headers))
                        continue
                    self._emit_trace(
                        started_at=started_at,
                        attempts=attempts,
                        success=False,
                        http_status=response.status_code,
                        response_id=None,
                        usage=DeepSeekUsage(),
                        error_kind=type(exc).__name__,
                    )
                    raise
                except ProviderResponseError as exc:
                    self._emit_trace(
                        started_at=started_at,
                        attempts=attempts,
                        success=False,
                        http_status=response.status_code,
                        response_id=None,
                        usage=DeepSeekUsage(),
                        error_kind=type(exc).__name__,
                    )
                    raise
                self._emit_trace(
                    started_at=started_at,
                    attempts=attempts,
                    success=True,
                    http_status=response.status_code,
                    response_id=response_id,
                    usage=usage,
                    error_kind=None,
                )
                return output_text

            error = self._http_error(response)
            if error.retryable and attempt < self.config.max_attempts:
                self._sleeper(self._backoff_seconds(attempt, response.headers))
                continue
            self._emit_trace(
                started_at=started_at,
                attempts=attempts,
                success=False,
                http_status=response.status_code,
                response_id=None,
                usage=DeepSeekUsage(),
                error_kind=type(error).__name__,
            )
            raise error

        raise ProviderTransientError(
            f"DeepSeek request exhausted retries (last HTTP status: {last_status})",
            status_code=last_status,
            retryable=True,
        )

    def _build_request_body(self, request: StructuredProviderRequest) -> bytes:
        payload = {
            "model": self.config.model,
            "instructions": request.system_instruction,
            "input": json.dumps(
                request.user_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.response_schema_name,
                    "schema": copy.deepcopy(request.response_schema),
                }
            },
            "reasoning": {"effort": self.config.reasoning_effort},
            "max_output_tokens": self.config.max_output_tokens,
            "stream": False,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "novel-character-generator/0.1.0.dev8",
        }

    def _parse_success(self, body: bytes) -> tuple[str, str | None, DeepSeekUsage]:
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderTransientError(
                "DeepSeek returned a non-JSON success response",
                status_code=200,
                retryable=True,
            ) from exc
        if not isinstance(value, Mapping):
            raise ProviderTransientError(
                "DeepSeek returned a non-object success response",
                status_code=200,
                retryable=True,
            )
        status = value.get("status")
        if status != "completed":
            incomplete_details = value.get("incomplete_details")
            incomplete_reason = (
                incomplete_details.get("reason")
                if isinstance(incomplete_details, Mapping)
                and isinstance(incomplete_details.get("reason"), str)
                else None
            )
            reason_suffix = f", reason={incomplete_reason!r}" if incomplete_reason else ""
            raise ProviderResponseError(
                f"DeepSeek response did not complete (status={status!r}{reason_suffix})",
                status_code=200,
            )
        output_texts: list[str] = []
        output = value.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, Mapping) or item.get("type") != "message":
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if (
                        isinstance(part, Mapping)
                        and part.get("type") == "output_text"
                        and isinstance(part.get("text"), str)
                    ):
                        output_texts.append(part["text"])
        output_text = "".join(output_texts)
        if not output_text.strip():
            raise ProviderTransientError(
                "DeepSeek returned an empty structured output",
                status_code=200,
                retryable=True,
            )
        response_id = value.get("id") if isinstance(value.get("id"), str) else None
        return output_text, response_id, self._parse_usage(value.get("usage"))

    @staticmethod
    def _parse_usage(value: Any) -> DeepSeekUsage:
        if not isinstance(value, Mapping):
            return DeepSeekUsage()
        input_details = value.get("input_tokens_details")
        output_details = value.get("output_tokens_details")
        return DeepSeekUsage(
            input_tokens=_optional_int(value.get("input_tokens")),
            cached_input_tokens=_optional_int(
                input_details.get("cached_tokens") if isinstance(input_details, Mapping) else None
            ),
            output_tokens=_optional_int(value.get("output_tokens")),
            reasoning_tokens=_optional_int(
                output_details.get("reasoning_tokens")
                if isinstance(output_details, Mapping)
                else None
            ),
            total_tokens=_optional_int(value.get("total_tokens")),
        )

    @staticmethod
    def _http_error(response: DeepSeekHTTPResponse) -> ProviderError:
        error_code = _extract_error_code(response.body)
        status = response.status_code
        message = f"DeepSeek API returned HTTP {status}"
        if error_code:
            message += f" ({error_code})"
        if status == 401:
            return ProviderAuthenticationError(
                message,
                status_code=status,
                error_code=error_code,
            )
        if status == 402:
            return ProviderInsufficientBalanceError(
                message,
                status_code=status,
                error_code=error_code,
            )
        if status in {400, 404, 422}:
            return ProviderBadRequestError(
                message,
                status_code=status,
                error_code=error_code,
            )
        if status == 429:
            return ProviderRateLimitError(
                message,
                status_code=status,
                retryable=True,
                error_code=error_code,
            )
        if status in RETRYABLE_STATUS_CODES:
            return ProviderTransientError(
                message,
                status_code=status,
                retryable=True,
                error_code=error_code,
            )
        return ProviderError(message, status_code=status, error_code=error_code)

    def _backoff_seconds(self, attempt: int, headers: Mapping[str, str]) -> float:
        retry_after = _retry_after_seconds(headers)
        if retry_after is not None:
            return min(retry_after, self.config.max_backoff_seconds)
        exponential = self.config.initial_backoff_seconds * (2 ** (attempt - 1))
        return min(exponential, self.config.max_backoff_seconds)

    def _emit_trace(
        self,
        *,
        started_at: float,
        attempts: int,
        success: bool,
        http_status: int | None,
        response_id: str | None,
        usage: DeepSeekUsage,
        error_kind: str | None,
    ) -> None:
        if self._trace_sink is None:
            return
        origin = urlsplit(self.config.base_url)
        trace = DeepSeekCallTrace(
            provider="deepseek",
            api="responses-v1",
            model=self.config.model,
            endpoint_origin=f"{origin.scheme}://{origin.netloc}",
            attempts=attempts,
            success=success,
            duration_ms=max(0, round((self._clock() - started_at) * 1000)),
            http_status=http_status,
            response_id=response_id,
            usage=usage,
            error_kind=error_kind,
        )
        self._trace_sink(trace)


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _extract_error_code(body: bytes) -> str | None:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping):
        return None
    error = value.get("error")
    if not isinstance(error, Mapping):
        return None
    code = error.get("code")
    if isinstance(code, str) and code and len(code) <= 80:
        return code
    return None


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    raw = next(
        (value for key, value in headers.items() if key.lower() == "retry-after"),
        None,
    )
    if raw is None:
        return None
    try:
        seconds = float(raw)
        return max(0.0, seconds)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        now = time.time()
        return max(0.0, retry_at.timestamp() - now)
