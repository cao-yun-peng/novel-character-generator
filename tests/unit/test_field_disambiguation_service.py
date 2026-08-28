from __future__ import annotations

from typing import Any

import pytest

from novel_character_generator.application.ports.field_disambiguation import (
    DetailedFieldDisambiguationResult,
    FieldDisambiguationDecision,
    FieldDisambiguationExecutionRequest,
    FieldDisambiguationResult,
    MappedFieldCandidate,
)
from novel_character_generator.application.ports.local_grounding import (
    GroundedEvidenceSpan,
    GroundedLocalFact,
    GroundedLocalPacket,
    GroundedMentionNode,
    LocalContextWindow,
)
from novel_character_generator.application.ports.model_provider import ModelCallMetadata
from novel_character_generator.application.services.field_disambiguation_service import (
    FieldDisambiguationContractError,
    FieldDisambiguationShadowService,
    validate_field_disambiguation_output,
)


def _packet(*, with_fact: bool = True) -> GroundedLocalPacket:
    fact = GroundedLocalFact(
        fact_id=f"gf_{'2' * 32}",
        local_fact_id="f1",
        local_entity_id="e1",
        evidence_quote="银色长发",
        evidence_span=GroundedEvidenceSpan(
            start=2,
            end=7,
            source_quote="银色长发",
            quote_hash="c" * 64,
        ),
        grounding_status="exact",
        raw_proposition="她有银色长发",
        coarse_family="hair",
        epistemic_status="asserted",
        local_context=LocalContextWindow(
            policy_version="local-context-sentence-window-v1",
            start=0,
            end=8,
            text="她有银色长发。",
            focus_start=2,
            focus_end=7,
            context_hash="d" * 64,
        ),
    )
    return GroundedLocalPacket(
        schema_version="grounded-local-packet-v1",
        run_id="run-2",
        source_document_version_id="source-2",
        chunk_id="chunk-2",
        grounding_policy_version="local-grounding-policy-v1",
        context_policy_version="local-context-sentence-window-v1",
        mention_nodes=(
            GroundedMentionNode(
                local_entity_id="e1",
                mention_quote="她",
                mention_kind="pronoun",
                representative_name="她",
                grounding_status="exact",
                occurrence_count=1,
                evidence_span=GroundedEvidenceSpan(
                    start=0,
                    end=1,
                    source_quote="她",
                    quote_hash="8" * 64,
                ),
            ),
        ),
        grounded_facts=(fact,) if with_fact else (),
        grounded_signals=(),
        rejected_items=(),
        deferred_items=(),
    )


def _result(
    *,
    field_path: str = "hair.color",
    referent_quote: str | None = "银色长发",
) -> FieldDisambiguationResult:
    return FieldDisambiguationResult(
        schema_version="field-disambiguation-result-v1",
        field_registry_version="visual-field-catalog-v1",
        chunk_id="chunk-2",
        decisions=(
            FieldDisambiguationDecision(
                fact_id=f"gf_{'2' * 32}",
                evidence_quote="银色长发",
                decision="map",
                mappings=(
                    MappedFieldCandidate(
                        mapping_id="m1",
                        semantic_unit_id="s1",
                        referent_kind="body_part",
                        referent_quote=referent_quote,
                        field_path=field_path,
                        normalized_value="银色",
                        evidence_quote="银色长发",
                    ),
                ),
                reason_code="explicit_atomic_mapping",
            ),
        ),
    )


class _Provider:
    version = "fake-m2-v1"
    model_config_version = "fake-m2-config-v1"
    prompt_version = "field-disambiguation-prompt-v1"
    prompt_hash = "e" * 64

    def __init__(self, output: FieldDisambiguationResult) -> None:
        self.output = output

    async def disambiguate_detailed(
        self, packet: GroundedLocalPacket
    ) -> DetailedFieldDisambiguationResult:
        del packet
        return DetailedFieldDisambiguationResult(
            output=self.output,
            metadata=ModelCallMetadata(
                wire_api="chat_completions",
                status="succeeded",
                latency_ms=1,
            ),
        )


@pytest.mark.asyncio
async def test_m2_shadow_service_returns_reproducible_side_effect_free_artifact() -> None:
    service = FieldDisambiguationShadowService(_Provider(_result()))  # type: ignore[arg-type]
    request = FieldDisambiguationExecutionRequest(
        schema_version="field-disambiguation-input-v1",
        data_policy_version="m2-shadow-data-v1",
        grounded_packet=_packet(),
    )
    first = await service.run(request)
    second = await service.run(request)
    assert first.node_id == "M2"
    assert first.status == "succeeded"
    assert first.counts.model_dump() == {
        "input_facts": 1,
        "mapped_facts": 1,
        "deferred_facts": 0,
        "rejected_facts": 0,
        "mappings": 1,
    }
    assert first.input_fingerprint == second.input_fingerprint
    assert first.output_fingerprint == second.output_fingerprint


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (_result(field_path="hair.colour"), "field_not_in_frozen_catalog"),
        (_result(referent_quote="不存在"), "field_disambiguation_referent_not_in_source"),
    ],
)
def test_m2_service_rejects_invalid_catalog_or_referent(
    result: FieldDisambiguationResult,
    error: str,
) -> None:
    with pytest.raises(FieldDisambiguationContractError, match=error):
        validate_field_disambiguation_output(_packet(), result)


@pytest.mark.asyncio
async def test_m2_service_does_not_call_provider_for_empty_packet() -> None:
    class _ExplodingProvider(_Provider):
        async def disambiguate_detailed(self, packet: GroundedLocalPacket) -> Any:
            raise AssertionError("provider_must_not_be_called")

    service = FieldDisambiguationShadowService(_ExplodingProvider(_result()))  # type: ignore[arg-type]
    request = FieldDisambiguationExecutionRequest(
        schema_version="field-disambiguation-input-v1",
        data_policy_version="m2-shadow-data-v1",
        grounded_packet=_packet(with_fact=False),
    )
    with pytest.raises(FieldDisambiguationContractError, match="m2_requires_grounded_facts"):
        await service.run(request)
