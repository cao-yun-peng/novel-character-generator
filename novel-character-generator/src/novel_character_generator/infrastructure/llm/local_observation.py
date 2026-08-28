from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import httpx
from pydantic import ValidationError

from novel_character_generator.application.ports.local_observation import (
    LOCAL_OBSERVATION_OUTPUT_SCHEMA_VERSION,
    LOCAL_OBSERVATION_PROMPT_VERSION,
    DetailedLocalObservationResult,
    LocalObservationDiscoveryInput,
    LocalObservationDiscoveryResult,
)
from novel_character_generator.infrastructure.llm.openai_compatible import (
    OpenAICompatibleStructuredClient,
    ProviderExtractionError,
    RawProviderExtraction,
    decode_provider_json,
)

_PROMPT_PATH = (
    Path(__file__).with_name("prompts") / "01-local-observation-discovery.system.md"
)
LOCAL_OBSERVATION_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_local_observation_request(
    request: LocalObservationDiscoveryInput,
    *,
    model: str,
    wire_api: Literal["chat_completions", "responses"] = "chat_completions",
    thinking_enabled: bool = False,
    reasoning_effort: Literal["none", "low", "medium", "high"] = "none",
    max_output_tokens: int = 8_192,
    system_prompt: str = LOCAL_OBSERVATION_SYSTEM_PROMPT,
) -> dict[str, object]:
    """Build the exact M1 request body without credentials or side effects."""

    schema = LocalObservationDiscoveryResult.model_json_schema()
    user_content = (
        "Output JSON schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}\n"
        "M1 input:\n"
        f"{request.model_dump_json()}"
    )
    if wire_api == "responses":
        return {
            "model": model,
            "input": f"{system_prompt}\n\n{user_content}",
            "reasoning": {"effort": reasoning_effort},
            "max_output_tokens": max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "local_observation_discovery_result",
                    "schema": schema,
                }
            },
        }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
        "reasoning_effort": reasoning_effort,
        "max_tokens": max_output_tokens,
        "temperature": 0,
    }


class OpenAICompatibleLocalObservationProvider:
    """M1 adapter; it has no database or Observation promotion authority."""

    prompt_version: Literal["local-observation-discovery-prompt-v1.1"] = (
        LOCAL_OBSERVATION_PROMPT_VERSION
    )

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 180.0,
        wire_api: Literal["chat_completions", "responses"] = "chat_completions",
        thinking_enabled: bool = False,
        reasoning_effort: Literal["none", "low", "medium", "high"] = "none",
        max_output_tokens: int = 8_192,
        total_deadline_seconds: float = 120.0,
        max_retries: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
        system_prompt: str = LOCAL_OBSERVATION_SYSTEM_PROMPT,
    ) -> None:
        self.provider = provider
        self.model = model
        self.wire_api = wire_api
        self.thinking_enabled = thinking_enabled
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.system_prompt = system_prompt
        self.prompt_hash = _sha256_text(system_prompt)
        model_config_payload = json.dumps(
            {
                "provider": provider,
                "model": model,
                "wire_api": wire_api,
                "thinking_enabled": thinking_enabled,
                "reasoning_effort": reasoning_effort,
                "max_output_tokens": max_output_tokens,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self.model_config_version = (
            f"local-observation-model-config-v1:{_sha256_text(model_config_payload)[:16]}"
        )
        self.version = (
            f"{provider}:{model}:{LOCAL_OBSERVATION_OUTPUT_SCHEMA_VERSION}:"
            f"{self.prompt_version}"
        )
        self._structured_client = OpenAICompatibleStructuredClient(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            wire_api=wire_api,
            total_deadline_seconds=total_deadline_seconds,
            max_retries=max_retries,
            transport=transport,
        )

    def _request_body(
        self, request: LocalObservationDiscoveryInput
    ) -> dict[str, object]:
        return build_local_observation_request(
            request,
            model=self.model,
            wire_api=self.wire_api,
            thinking_enabled=self.thinking_enabled,
            reasoning_effort=self.reasoning_effort,
            max_output_tokens=self.max_output_tokens,
            system_prompt=self.system_prompt,
        )

    def process_raw_response(
        self, response: RawProviderExtraction
    ) -> LocalObservationDiscoveryResult:
        try:
            decoded = decode_provider_json(response.message_content)
            return LocalObservationDiscoveryResult.model_validate(decoded)
        except (TypeError, ValueError, ValidationError) as error:
            raise ProviderExtractionError(
                "local_observation_schema_validation_failed",
                retryable=True,
            ) from error

    async def discover_detailed(
        self, request: LocalObservationDiscoveryInput
    ) -> DetailedLocalObservationResult:
        validated = await self._structured_client.request_validated(
            self._request_body(request),
            self.process_raw_response,
        )
        return DetailedLocalObservationResult(
            output=validated.output,
            metadata=validated.raw.metadata,
            raw_response=validated.raw.response_payload,
            raw_message_content=validated.raw.message_content,
        )
