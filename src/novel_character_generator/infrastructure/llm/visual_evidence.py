from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import httpx
from pydantic import ValidationError

from novel_character_generator.application.ports.visual_evidence import (
    VISUAL_EVIDENCE_MODEL_WIRE_SCHEMA_VERSION,
    VISUAL_EVIDENCE_OUTPUT_SCHEMA_VERSION,
    VISUAL_EVIDENCE_PROMPT_VERSION,
    DetailedVisualEvidenceResult,
    GroundedEvidenceCandidate,
    VisualEvidenceDiscoveryInput,
    VisualEvidenceDiscoveryResult,
    VisualEvidenceMention,
    VisualEvidenceModelOutput,
)
from novel_character_generator.infrastructure.llm.structured_client import (
    OpenAICompatibleStructuredClient,
    ProviderExtractionError,
    RawProviderExtraction,
    decode_provider_json,
)

_PROMPT_PATH = Path(__file__).with_name("prompts") / "01-visual-evidence-discovery.system.md"
VISUAL_EVIDENCE_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def materialize_visual_evidence_result(
    request: VisualEvidenceDiscoveryInput,
    model_output: VisualEvidenceModelOutput,
) -> VisualEvidenceDiscoveryResult:
    used_owner_indices = {
        candidate.owner_index
        for candidate in model_output.evidence_candidates
        if candidate.owner_index is not None
    }
    owner_map = {
        old_index: f"m{new_index}"
        for new_index, old_index in enumerate(sorted(used_owner_indices), start=1)
    }
    mentions = tuple(
        VisualEvidenceMention(mention_id=owner_map[index], mention_quote=item.mention_quote)
        for index, item in enumerate(model_output.mentions)
        if index in used_owner_indices
    )
    candidates = tuple(
        GroundedEvidenceCandidate(
            candidate_id=f"c{index}",
            local_owner_id=(owner_map[item.owner_index] if item.owner_index is not None else None),
            evidence_quote=item.evidence_quote,
        )
        for index, item in enumerate(model_output.evidence_candidates, start=1)
    )
    return VisualEvidenceDiscoveryResult(
        schema_version=VISUAL_EVIDENCE_OUTPUT_SCHEMA_VERSION,
        chunk_id=request.chunk_id,
        mentions=mentions,
        evidence_candidates=candidates,
    )


def build_visual_evidence_request(
    request: VisualEvidenceDiscoveryInput,
    *,
    model: str,
    wire_api: Literal["chat_completions", "responses"] = "chat_completions",
    thinking_enabled: bool = False,
    reasoning_effort: Literal["none", "low", "medium", "high"] = "none",
    max_output_tokens: int = 4_096,
    system_prompt: str = VISUAL_EVIDENCE_SYSTEM_PROMPT,
) -> dict[str, object]:
    schema = VisualEvidenceModelOutput.model_json_schema()
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
                    "name": "visual_evidence_discovery",
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


class OpenAICompatibleVisualEvidenceProvider:
    prompt_version = VISUAL_EVIDENCE_PROMPT_VERSION

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
        max_output_tokens: int = 4_096,
        total_deadline_seconds: float = 120.0,
        max_retries: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
        system_prompt: str = VISUAL_EVIDENCE_SYSTEM_PROMPT,
    ) -> None:
        self.provider = provider
        self.model = model
        self.wire_api = wire_api
        self.thinking_enabled = thinking_enabled
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.system_prompt = system_prompt
        self.prompt_hash = _sha256_text(system_prompt)
        config_payload = json.dumps(
            {
                "provider": provider,
                "model": model,
                "wire_api": wire_api,
                "thinking_enabled": thinking_enabled,
                "reasoning_effort": reasoning_effort,
                "max_output_tokens": max_output_tokens,
                "wire_schema_version": VISUAL_EVIDENCE_MODEL_WIRE_SCHEMA_VERSION,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self.model_config_version = (
            "visual-evidence-model-config-v2:"
            f"{_sha256_text(config_payload)[:16]}"
        )
        self.version = (
            f"{provider}:{model}:{VISUAL_EVIDENCE_MODEL_WIRE_SCHEMA_VERSION}:"
            f"{VISUAL_EVIDENCE_OUTPUT_SCHEMA_VERSION}:{self.prompt_version}"
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

    def _request_body(self, request: VisualEvidenceDiscoveryInput) -> dict[str, object]:
        return build_visual_evidence_request(
            request,
            model=self.model,
            wire_api=self.wire_api,
            thinking_enabled=self.thinking_enabled,
            reasoning_effort=self.reasoning_effort,
            max_output_tokens=self.max_output_tokens,
            system_prompt=self.system_prompt,
        )

    def process_raw_response(
        self, request: VisualEvidenceDiscoveryInput, response: RawProviderExtraction
    ) -> VisualEvidenceDiscoveryResult:
        try:
            decoded = decode_provider_json(response.message_content)
            model_output = VisualEvidenceModelOutput.model_validate(decoded)
            return materialize_visual_evidence_result(request, model_output)
        except (TypeError, ValueError, ValidationError) as error:
            raise ProviderExtractionError(
                "visual_evidence_schema_validation_failed", retryable=True
            ) from error

    async def discover_detailed(
        self, request: VisualEvidenceDiscoveryInput
    ) -> DetailedVisualEvidenceResult:
        validated = await self._structured_client.request_validated(
            self._request_body(request),
            lambda response: self.process_raw_response(request, response),
        )
        return DetailedVisualEvidenceResult(
            output=validated.output,
            metadata=validated.raw.metadata,
            raw_response=validated.raw.response_payload,
            raw_message_content=validated.raw.message_content,
        )
