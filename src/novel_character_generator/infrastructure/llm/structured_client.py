import asyncio
import json
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from novel_character_generator.application.ports.model_provider import (
    ModelCallMetadata,
    ModelTokenUsage,
)

_JSON_FENCE_PATTERN = re.compile(
    r"```(?:json|application/json)?\s*(.*?)```",
    flags=re.IGNORECASE | re.DOTALL,
)

@dataclass(frozen=True)
class RawProviderExtraction:
    """Unmodified provider response retained for diagnostics and fixtures."""

    response_payload: object
    message_content: object
    metadata: ModelCallMetadata


class ProviderExtractionError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool, attempts: int = 1) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.attempts = attempts


@dataclass(frozen=True)
class ValidatedProviderCall[ValidatedOutputT]:
    """One validated structured-model result plus its unmodified response."""

    output: ValidatedOutputT
    raw: RawProviderExtraction


def _balanced_json_candidates(text: str) -> Iterator[str]:
    """Yield complete top-level JSON containers embedded in provider prose.

    The scanner understands quoted strings and escapes, so braces appearing in
    evidence quotes do not terminate a candidate. It never fills in a missing
    closing delimiter: truncated output remains an error and is retried.
    """

    cursor = 0
    while cursor < len(text):
        object_start = text.find("{", cursor)
        array_start = text.find("[", cursor)
        starts = [item for item in (object_start, array_start) if item >= 0]
        if not starts:
            return
        start = min(starts)
        stack: list[str] = []
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            character = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == '"':
                in_string = True
            elif character in "[{":
                stack.append(character)
            elif character in "]}":
                expected = "[" if character == "]" else "{"
                if not stack or stack[-1] != expected:
                    cursor = index + 1
                    break
                stack.pop()
                if not stack:
                    yield text[start : index + 1]
                    cursor = index + 1
                    break
        else:
            return


def _remove_trailing_json_commas(text: str) -> str:
    """Remove only commas immediately before a JSON closing delimiter."""

    repaired: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if in_string:
            repaired.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            repaired.append(character)
            index += 1
            continue
        if character == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "]}":
                index += 1
                continue
        repaired.append(character)
        index += 1
    return "".join(repaired)


def decode_provider_json(content: object) -> object:
    """Decode common non-semantic JSON formatting mistakes conservatively.

    Supported recovery is limited to BOM/whitespace, Markdown JSON fences,
    explanatory text around one complete JSON container, trailing commas, and
    one layer of JSON string encoding. Missing delimiters, unquoted keys, and
    other ambiguous mutations are deliberately rejected instead of guessed.
    """

    if isinstance(content, (dict, list)):
        return content
    if not isinstance(content, str):
        raise ValueError("invalid_provider_content")
    normalized = content.lstrip("\ufeff").strip()
    candidates = [normalized]
    candidates.extend(match.group(1).strip() for match in _JSON_FENCE_PATTERN.finditer(normalized))
    candidates.extend(_balanced_json_candidates(normalized))
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        variants = (candidate, _remove_trailing_json_commas(candidate))
        for variant in dict.fromkeys(variants):
            try:
                decoded = json.loads(variant)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, str):
                nested = decoded.lstrip("\ufeff").strip()
                if nested.startswith(("{", "[")):
                    try:
                        return json.loads(_remove_trailing_json_commas(nested))
                    except json.JSONDecodeError:
                        continue
            return decoded
    raise ValueError("invalid_provider_json")


def _integer(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _token_usage(payload: dict[str, Any]) -> ModelTokenUsage:
    raw = payload.get("usage")
    if not isinstance(raw, dict):
        return ModelTokenUsage()
    input_tokens = _integer(raw.get("input_tokens", raw.get("prompt_tokens")))
    output_tokens = _integer(raw.get("output_tokens", raw.get("completion_tokens")))
    input_details = raw.get("input_tokens_details", raw.get("prompt_tokens_details"))
    output_details = raw.get("output_tokens_details", raw.get("completion_tokens_details"))
    cache_hit_tokens = _integer(raw.get("prompt_cache_hit_tokens"))
    cache_miss_tokens = _integer(raw.get("prompt_cache_miss_tokens"))
    reasoning_tokens = 0
    if isinstance(input_details, dict):
        cache_hit_tokens = max(
            cache_hit_tokens,
            _integer(input_details.get("cached_tokens", input_details.get("cache_read_tokens"))),
        )
    if isinstance(output_details, dict):
        reasoning_tokens = _integer(output_details.get("reasoning_tokens"))
    return ModelTokenUsage(
        input_tokens=input_tokens,
        cache_hit_tokens=cache_hit_tokens,
        cache_miss_tokens=cache_miss_tokens,
        reasoning_tokens=reasoning_tokens,
        output_tokens=output_tokens,
        total_tokens=_integer(raw.get("total_tokens")) or input_tokens + output_tokens,
    )


def _responses_text(payload: dict[str, Any]) -> object:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    output = payload.get("output")
    if not isinstance(output, list):
        return None
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and part.get("type") in {"output_text", "text", None}:
                texts.append(text)
    return "".join(texts) if texts else None


def _provider_response_parts(
    payload: object,
    *,
    wire_api: Literal["chat_completions", "responses"],
) -> tuple[object, str, str | None]:
    if not isinstance(payload, dict):
        raise ProviderExtractionError("invalid_provider_response", retryable=True)
    if wire_api == "responses":
        status = payload.get("status")
        normalized_status = status if isinstance(status, str) else "completed"
        incomplete_details = payload.get("incomplete_details")
        finish_reason = None
        if isinstance(incomplete_details, dict) and isinstance(
            incomplete_details.get("reason"), str
        ):
            finish_reason = incomplete_details["reason"]
        if normalized_status != "completed":
            raise ProviderExtractionError(f"provider_response_{normalized_status}", retryable=True)
        content = _responses_text(payload)
        if not isinstance(content, str) or not content.strip():
            raise ProviderExtractionError("empty_provider_content", retryable=True)
        return content, normalized_status, finish_reason
    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderExtractionError("invalid_provider_response", retryable=True) from error
    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    if finish_reason in {"length", "content_filter"}:
        raise ProviderExtractionError(
            f"provider_finish_{finish_reason}", retryable=finish_reason == "length"
        )
    if not isinstance(content, str) or not content.strip():
        raise ProviderExtractionError("empty_provider_content", retryable=True)
    return content, "completed", finish_reason if isinstance(finish_reason, str) else None


class OpenAICompatibleStructuredClient:
    """Reusable transport/retry boundary for one strict JSON request body.

    Node adapters own prompts and Pydantic schemas. This client owns only HTTP,
    provider response decoding metadata, total deadline, and bounded retries.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 180.0,
        wire_api: Literal["chat_completions", "responses"] = "chat_completions",
        total_deadline_seconds: float = 120.0,
        max_retries: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.wire_api = wire_api
        self.total_deadline_seconds = total_deadline_seconds
        self.max_retries = max_retries
        self.transport = transport

    async def _request_once(
        self,
        client: httpx.AsyncClient,
        request_body: dict[str, object],
    ) -> RawProviderExtraction:
        started = time.perf_counter()
        endpoint = "responses" if self.wire_api == "responses" else "chat/completions"
        response = await client.post(endpoint, json=request_body)
        response.raise_for_status()
        try:
            payload: object = response.json()
        except json.JSONDecodeError as error:
            raise ProviderExtractionError("invalid_provider_json_body", retryable=True) from error
        content, status, finish_reason = _provider_response_parts(
            payload,
            wire_api=self.wire_api,
        )
        payload_mapping = payload if isinstance(payload, dict) else {}
        request_id = response.headers.get("x-request-id")
        if request_id is None and isinstance(payload_mapping.get("id"), str):
            request_id = payload_mapping["id"]
        return RawProviderExtraction(
            response_payload=payload,
            message_content=content,
            metadata=ModelCallMetadata(
                wire_api=self.wire_api,
                provider_request_id=request_id,
                response_model=(
                    payload_mapping.get("model")
                    if isinstance(payload_mapping.get("model"), str)
                    else None
                ),
                status=status,
                finish_reason=finish_reason,
                latency_ms=(time.perf_counter() - started) * 1_000,
                usage=_token_usage(payload_mapping),
            ),
        )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout_seconds,
            transport=self.transport,
        )

    async def request_raw(self, request_body: dict[str, object]) -> RawProviderExtraction:
        try:
            async with asyncio.timeout(self.total_deadline_seconds):
                async with self._client() as client:
                    return await self._request_once(client, request_body)
        except TimeoutError as error:
            raise ProviderExtractionError(
                "provider_total_deadline_exceeded", retryable=True
            ) from error

    async def request_validated[ValidatedOutputT](
        self,
        request_body: dict[str, object],
        validator: Callable[[RawProviderExtraction], ValidatedOutputT],
    ) -> ValidatedProviderCall[ValidatedOutputT]:
        started = time.perf_counter()
        attempts = 0
        last_error: ProviderExtractionError | None = None
        try:
            async with asyncio.timeout(self.total_deadline_seconds):
                async with self._client() as client:
                    while attempts <= self.max_retries:
                        attempts += 1
                        try:
                            raw = await self._request_once(client, request_body)
                            output = validator(raw)
                            metadata = raw.metadata.model_copy(
                                update={
                                    "attempts": attempts,
                                    "latency_ms": (time.perf_counter() - started) * 1_000,
                                }
                            )
                            return ValidatedProviderCall(
                                output=output,
                                raw=RawProviderExtraction(
                                    response_payload=raw.response_payload,
                                    message_content=raw.message_content,
                                    metadata=metadata,
                                ),
                            )
                        except httpx.HTTPStatusError as error:
                            status = error.response.status_code
                            last_error = ProviderExtractionError(
                                f"provider_http_{status}",
                                retryable=status in {408, 409, 429} or status >= 500,
                                attempts=attempts,
                            )
                        except httpx.TransportError as error:
                            last_error = ProviderExtractionError(
                                "provider_transport_error",
                                retryable=True,
                                attempts=attempts,
                            )
                            last_error.__cause__ = error
                        except ProviderExtractionError as error:
                            last_error = ProviderExtractionError(
                                error.code,
                                retryable=error.retryable,
                                attempts=attempts,
                            )
                            last_error.__cause__ = error
                        if not last_error.retryable or attempts > self.max_retries:
                            raise last_error
        except TimeoutError as error:
            raise ProviderExtractionError(
                "provider_total_deadline_exceeded",
                retryable=True,
                attempts=max(attempts, 1),
            ) from error
        if last_error is not None:
            raise last_error
        raise ProviderExtractionError(
            "provider_extraction_failed",
            retryable=False,
            attempts=max(attempts, 1),
        )
