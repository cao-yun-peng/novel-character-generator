from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import httpx
from pydantic import ValidationError

from novel_character_generator.application.ports.field_disambiguation import (
    FIELD_DISAMBIGUATION_MODEL_WIRE_SCHEMA_VERSION,
    FIELD_DISAMBIGUATION_OUTPUT_SCHEMA_VERSION,
    FIELD_DISAMBIGUATION_PROMPT_VERSION,
    DetailedFieldDisambiguationResult,
    FieldCatalogWireEntry,
    FieldDisambiguationDecision,
    FieldDisambiguationModelFact,
    FieldDisambiguationModelOutput,
    FieldDisambiguationResult,
    MappedFieldCandidate,
)
from novel_character_generator.application.ports.local_grounding import GroundedLocalPacket
from novel_character_generator.domain.policies.visual_field_catalog import (
    VISUAL_FIELD_CATALOG_VERSION,
    is_catalog_field,
    visual_field_catalog_payload,
)
from novel_character_generator.infrastructure.llm.structured_client import (
    OpenAICompatibleStructuredClient,
    ProviderExtractionError,
    RawProviderExtraction,
    decode_provider_json,
)

_PROMPT_PATH = Path(__file__).with_name("prompts") / "02-field-disambiguation.system.md"
FIELD_DISAMBIGUATION_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _model_facts(packet: GroundedLocalPacket) -> list[FieldDisambiguationModelFact]:
    return [
        FieldDisambiguationModelFact(
            evidence_quote=fact.evidence_quote,
            raw_proposition=fact.raw_proposition,
            coarse_family=fact.coarse_family,
            epistemic_status=fact.epistemic_status,
            local_context=fact.local_context.text,
        )
        for fact in packet.grounded_facts
    ]


def _catalog_entries() -> list[FieldCatalogWireEntry]:
    return [FieldCatalogWireEntry.model_validate(item) for item in visual_field_catalog_payload()]


def materialize_field_disambiguation_result(
    packet: GroundedLocalPacket,
    model_output: FieldDisambiguationModelOutput,
) -> FieldDisambiguationResult:
    """Inject immutable grounded provenance and local IDs after M2 semantic decisions."""

    fact_count = len(packet.grounded_facts)
    fact_indices = [item.fact_index for item in model_output.decisions]
    if any(index >= fact_count for index in fact_indices):
        raise ValueError("field_disambiguation_fact_index_out_of_range")
    if len(fact_indices) != len(set(fact_indices)):
        raise ValueError("duplicate_field_disambiguation_fact_index")
    if set(fact_indices) != set(range(fact_count)):
        raise ValueError("incomplete_field_disambiguation_fact_indices")

    decisions: list[FieldDisambiguationDecision] = []
    for model_decision in sorted(model_output.decisions, key=lambda item: item.fact_index):
        fact = packet.grounded_facts[model_decision.fact_index]
        semantic_bindings: dict[int, tuple[str, str | None]] = {}
        dimensions: set[tuple[int, str]] = set()
        for mapping in model_decision.mappings:
            if not is_catalog_field(mapping.field_path):
                raise ValueError(f"field_not_in_frozen_catalog:{mapping.field_path}")
            if mapping.referent_quote is not None and (
                mapping.referent_quote not in fact.evidence_quote
                and mapping.referent_quote not in fact.local_context.text
            ):
                raise ValueError("field_disambiguation_referent_not_in_source")
            binding = (mapping.referent_kind, mapping.referent_quote)
            prior_binding = semantic_bindings.setdefault(mapping.semantic_unit_index, binding)
            if prior_binding != binding:
                raise ValueError("semantic_unit_has_conflicting_referent")
            dimension = (mapping.semantic_unit_index, mapping.field_path)
            if dimension in dimensions:
                raise ValueError("duplicate_semantic_unit_dimension")
            dimensions.add(dimension)
        ordered_mappings = sorted(
            model_decision.mappings,
            key=lambda item: (
                item.semantic_unit_index,
                item.referent_kind,
                item.referent_quote or "",
                item.field_path,
                item.normalized_value,
            ),
        )
        semantic_index_map = {
            semantic_index: index
            for index, semantic_index in enumerate(
                sorted({item.semantic_unit_index for item in ordered_mappings}),
                start=1,
            )
        }
        mappings = tuple(
            MappedFieldCandidate(
                mapping_id=f"m{mapping_index}",
                semantic_unit_id=f"s{semantic_index_map[item.semantic_unit_index]}",
                referent_kind=item.referent_kind,
                referent_quote=item.referent_quote,
                field_path=item.field_path,
                normalized_value=item.normalized_value,
                evidence_quote=fact.evidence_quote,
            )
            for mapping_index, item in enumerate(ordered_mappings, start=1)
        )
        decisions.append(
            FieldDisambiguationDecision(
                fact_id=fact.fact_id,
                evidence_quote=fact.evidence_quote,
                decision=model_decision.decision,
                mappings=mappings,
                reason_code=model_decision.reason_code,
            )
        )
    return FieldDisambiguationResult(
        schema_version=FIELD_DISAMBIGUATION_OUTPUT_SCHEMA_VERSION,
        field_registry_version=VISUAL_FIELD_CATALOG_VERSION,
        chunk_id=packet.chunk_id,
        decisions=tuple(decisions),
    )


def build_field_disambiguation_request(
    packet: GroundedLocalPacket,
    *,
    model: str,
    wire_api: Literal["chat_completions", "responses"] = "chat_completions",
    thinking_enabled: bool = False,
    reasoning_effort: Literal["none", "low", "medium", "high"] = "none",
    max_output_tokens: int = 8_192,
    system_prompt: str = FIELD_DISAMBIGUATION_SYSTEM_PROMPT,
) -> dict[str, object]:
    """Build an M2 request without stable IDs, duplicated output quotes, or version chatter."""

    schema = FieldDisambiguationModelOutput.model_json_schema()
    business_input = {
        "facts": [item.model_dump(mode="json") for item in _model_facts(packet)],
        "canonical_field_catalog": [
            item.model_dump(mode="json") for item in _catalog_entries()
        ],
    }
    input_json = json.dumps(business_input, ensure_ascii=False, separators=(",", ":"))
    if wire_api == "responses":
        return {
            "model": model,
            "input": f"{system_prompt}\n\nM2 input:\n{input_json}",
            "reasoning": {"effort": reasoning_effort},
            "max_output_tokens": max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "field_disambiguation_result",
                    "schema": schema,
                }
            },
        }
    user_content = (
        "Output JSON schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}\n"
        "M2 input:\n"
        f"{input_json}"
    )
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


class OpenAICompatibleFieldDisambiguationProvider:
    """M2 adapter with no identity, scope, persistence, or promotion authority."""

    prompt_version: Literal["field-disambiguation-prompt-v1"] = (
        FIELD_DISAMBIGUATION_PROMPT_VERSION
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
        system_prompt: str = FIELD_DISAMBIGUATION_SYSTEM_PROMPT,
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
                "wire_schema_version": FIELD_DISAMBIGUATION_MODEL_WIRE_SCHEMA_VERSION,
                "field_registry_version": VISUAL_FIELD_CATALOG_VERSION,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self.model_config_version = (
            f"field-disambiguation-model-config-v1:{_sha256_text(config_payload)[:16]}"
        )
        self.version = (
            f"{provider}:{model}:{FIELD_DISAMBIGUATION_MODEL_WIRE_SCHEMA_VERSION}:"
            f"{FIELD_DISAMBIGUATION_OUTPUT_SCHEMA_VERSION}:{VISUAL_FIELD_CATALOG_VERSION}:"
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

    def _request_body(self, packet: GroundedLocalPacket) -> dict[str, object]:
        return build_field_disambiguation_request(
            packet,
            model=self.model,
            wire_api=self.wire_api,
            thinking_enabled=self.thinking_enabled,
            reasoning_effort=self.reasoning_effort,
            max_output_tokens=self.max_output_tokens,
            system_prompt=self.system_prompt,
        )

    def process_raw_response(
        self,
        packet: GroundedLocalPacket,
        response: RawProviderExtraction,
    ) -> FieldDisambiguationResult:
        try:
            decoded = decode_provider_json(response.message_content)
            model_output = FieldDisambiguationModelOutput.model_validate(decoded)
            return materialize_field_disambiguation_result(packet, model_output)
        except (TypeError, ValueError, ValidationError) as error:
            raise ProviderExtractionError(
                "field_disambiguation_schema_validation_failed",
                retryable=True,
            ) from error

    async def disambiguate_detailed(
        self, packet: GroundedLocalPacket
    ) -> DetailedFieldDisambiguationResult:
        validated = await self._structured_client.request_validated(
            self._request_body(packet),
            lambda response: self.process_raw_response(packet, response),
        )
        return DetailedFieldDisambiguationResult(
            output=validated.output,
            metadata=validated.raw.metadata,
            raw_response=validated.raw.response_payload,
            raw_message_content=validated.raw.message_content,
        )
