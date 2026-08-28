from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import httpx
from pydantic import ValidationError

from novel_character_generator.application.ports.local_observation import (
    LOCAL_OBSERVATION_MODEL_WIRE_SCHEMA_VERSION,
    LOCAL_OBSERVATION_OUTPUT_SCHEMA_VERSION,
    LOCAL_OBSERVATION_PROMPT_VERSION,
    DetailedLocalObservationResult,
    LocalObservationDiscoveryInput,
    LocalObservationDiscoveryResult,
    LocalObservationEntity,
    LocalObservationFact,
    LocalObservationModelOutput,
    LocalObservationTemporalSignal,
    LocalObservationUnresolvedItem,
)
from novel_character_generator.infrastructure.llm.structured_client import (
    OpenAICompatibleStructuredClient,
    ProviderExtractionError,
    RawProviderExtraction,
    decode_provider_json,
)

_PROMPT_PATH = Path(__file__).with_name("prompts") / "01-local-observation-discovery.system.md"
LOCAL_OBSERVATION_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def materialize_local_observation_result(
    request: LocalObservationDiscoveryInput,
    model_output: LocalObservationModelOutput,
) -> LocalObservationDiscoveryResult:
    """Add deterministic transport fields after M1 has made semantic decisions."""

    used_owner_indices = {item.owner_index for item in model_output.facts}
    used_owner_indices.update(
        item.owner_index for item in model_output.temporal_signals if item.owner_index is not None
    )
    used_owner_indices.update(
        item.owner_index for item in model_output.unresolved_items if item.owner_index is not None
    )
    owner_index_map = {
        old_index: new_index
        for new_index, old_index in enumerate(sorted(used_owner_indices), start=1)
    }
    entities = [
        LocalObservationEntity(
            local_entity_id=f"e{owner_index_map[index]}",
            mention_quote=item.mention_quote,
            mention_kind=item.mention_kind,
            representative_name=item.mention_quote,
        )
        for index, item in enumerate(model_output.entities)
        if index in used_owner_indices
    ]
    facts = [
        LocalObservationFact(
            local_fact_id=f"f{index}",
            entity_ref=f"e{owner_index_map[item.owner_index]}",
            evidence_quote=item.evidence_quote,
            raw_proposition=item.raw_proposition,
            coarse_family=item.coarse_family,
            epistemic_status=item.epistemic_status,
        )
        for index, item in enumerate(model_output.facts, start=1)
    ]
    temporal_signals: list[LocalObservationTemporalSignal] = []
    for index, item in enumerate(model_output.temporal_signals, start=1):
        owner_index = item.owner_index
        fact_index = item.fact_index
        if fact_index is None:
            containing_fact_indices = [
                fact_index
                for fact_index, fact in enumerate(model_output.facts)
                if item.evidence_quote in fact.evidence_quote
                and (owner_index is None or fact.owner_index == owner_index)
            ]
            if len(containing_fact_indices) == 1:
                fact_index = containing_fact_indices[0]
        if fact_index is not None:
            owner_index = model_output.facts[fact_index].owner_index
        temporal_signals.append(
            LocalObservationTemporalSignal(
                local_signal_id=f"t{index}",
                entity_ref=(
                    f"e{owner_index_map[owner_index]}" if owner_index is not None else None
                ),
                fact_ref=f"f{fact_index + 1}" if fact_index is not None else None,
                evidence_quote=item.evidence_quote,
                signal_kind=item.signal_kind,
                raw_label=item.evidence_quote,
            )
        )
    unresolved_items = [
        LocalObservationUnresolvedItem(
            local_item_id=f"u{index}",
            entity_ref=(
                f"e{owner_index_map[item.owner_index]}" if item.owner_index is not None else None
            ),
            evidence_quote=item.evidence_quote,
            raw_proposition=item.raw_proposition,
            reason_code=item.reason_code,
        )
        for index, item in enumerate(model_output.unresolved_items, start=1)
    ]
    return LocalObservationDiscoveryResult(
        schema_version=LOCAL_OBSERVATION_OUTPUT_SCHEMA_VERSION,
        chunk_id=request.chunk_id,
        entities=entities,
        facts=facts,
        temporal_signals=temporal_signals,
        unresolved_items=unresolved_items,
    )


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

    schema = LocalObservationModelOutput.model_json_schema()
    user_content = (
        "Output JSON schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}\n"
        "Novel chunk:\n"
        f"{request.chunk_text}"
    )
    if wire_api == "responses":
        return {
            "model": model,
            "input": f"{system_prompt}\n\nNovel chunk:\n{request.chunk_text}",
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

    prompt_version: Literal["local-observation-discovery-prompt-v1.6"] = (
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
                "wire_schema_version": LOCAL_OBSERVATION_MODEL_WIRE_SCHEMA_VERSION,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self.model_config_version = (
            f"local-observation-model-config-v1:{_sha256_text(model_config_payload)[:16]}"
        )
        self.version = (
            f"{provider}:{model}:{LOCAL_OBSERVATION_MODEL_WIRE_SCHEMA_VERSION}:"
            f"{LOCAL_OBSERVATION_OUTPUT_SCHEMA_VERSION}:"
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

    def _request_body(self, request: LocalObservationDiscoveryInput) -> dict[str, object]:
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
        self,
        request: LocalObservationDiscoveryInput,
        response: RawProviderExtraction,
    ) -> LocalObservationDiscoveryResult:
        try:
            decoded = decode_provider_json(response.message_content)
            model_output = LocalObservationModelOutput.model_validate(decoded)
            return materialize_local_observation_result(request, model_output)
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
            lambda response: self.process_raw_response(request, response),
        )
        return DetailedLocalObservationResult(
            output=validated.output,
            metadata=validated.raw.metadata,
            raw_response=validated.raw.response_payload,
            raw_message_content=validated.raw.message_content,
        )
