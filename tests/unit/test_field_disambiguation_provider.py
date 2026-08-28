import json

import httpx
import pytest

from novel_character_generator.application.ports.field_disambiguation import (
    FieldDisambiguationModelOutput,
)
from novel_character_generator.application.ports.local_grounding import (
    GroundedEvidenceSpan,
    GroundedLocalFact,
    GroundedLocalPacket,
    GroundedMentionNode,
    LocalContextWindow,
)
from novel_character_generator.infrastructure.llm.field_disambiguation import (
    FIELD_DISAMBIGUATION_SYSTEM_PROMPT,
    OpenAICompatibleFieldDisambiguationProvider,
    build_field_disambiguation_request,
    materialize_field_disambiguation_result,
)


def _packet() -> GroundedLocalPacket:
    quote = "蓝色粗布短衫"
    return GroundedLocalPacket(
        schema_version="grounded-local-packet-v1",
        run_id="run-1",
        source_document_version_id="source-1",
        chunk_id="chunk-1",
        grounding_policy_version="local-grounding-policy-v1",
        context_policy_version="local-context-sentence-window-v1",
        mention_nodes=(
            GroundedMentionNode(
                local_entity_id="e1",
                mention_quote="他",
                mention_kind="pronoun",
                representative_name="他",
                grounding_status="exact",
                occurrence_count=1,
                evidence_span=GroundedEvidenceSpan(
                    start=0,
                    end=1,
                    source_quote="他",
                    quote_hash="9" * 64,
                ),
            ),
        ),
        grounded_facts=(
            GroundedLocalFact(
                fact_id=f"gf_{'1' * 32}",
                local_fact_id="f1",
                local_entity_id="e1",
                evidence_quote=quote,
                evidence_span=GroundedEvidenceSpan(
                    start=2,
                    end=8,
                    source_quote=quote,
                    quote_hash="a" * 64,
                ),
                grounding_status="exact",
                raw_proposition="他穿着蓝色粗布短衫",
                coarse_family="clothing",
                epistemic_status="asserted",
                local_context=LocalContextWindow(
                    policy_version="local-context-sentence-window-v1",
                    start=0,
                    end=9,
                    text="他穿蓝色粗布短衫。",
                    focus_start=2,
                    focus_end=8,
                    context_hash="b" * 64,
                ),
            ),
        ),
        grounded_signals=(),
        rejected_items=(),
        deferred_items=(),
    )


def _payload() -> dict[str, object]:
    return {
        "decisions": [
            {
                "fact_index": 0,
                "decision": "map",
                "mappings": [
                    {
                        "semantic_unit_index": 9,
                        "referent_kind": "garment",
                        "referent_quote": "粗布短衫",
                        "field_path": "clothing.material",
                        "normalized_value": "粗布",
                    },
                    {
                        "semantic_unit_index": 9,
                        "referent_kind": "garment",
                        "referent_quote": "粗布短衫",
                        "field_path": "clothing.type",
                        "normalized_value": "短衫",
                    },
                    {
                        "semantic_unit_index": 9,
                        "referent_kind": "garment",
                        "referent_quote": "粗布短衫",
                        "field_path": "clothing.color",
                        "normalized_value": "蓝色",
                    },
                ],
                "reason_code": "explicit_atomic_mapping",
            }
        ]
    }


def test_m2_request_uses_catalog_and_minimal_index_wire() -> None:
    body = build_field_disambiguation_request(_packet(), model="model-v1")
    serialized = json.dumps(body, ensure_ascii=False)
    user_content = body["messages"][1]["content"]
    assert "蓝色粗布短衫" in user_content
    assert "canonical_field_catalog" in user_content
    assert "visual-field-catalog-v1" not in serialized
    assert f"gf_{'1' * 32}" not in serialized
    assert "chunk-1" not in serialized
    assert "fact_id" not in serialized
    assert "mapping_id" not in serialized
    assert "semantic_unit_id" not in serialized
    assert "fact_index" in serialized
    assert "semantic_unit_index" in serialized
    assert "field_path" in user_content
    assert "value_type" in user_content


def test_m2_materializer_injects_and_stabilizes_mechanical_fields() -> None:
    model_output = FieldDisambiguationModelOutput.model_validate(_payload())
    result = materialize_field_disambiguation_result(_packet(), model_output)
    decision = result.decisions[0]
    assert decision.fact_id == f"gf_{'1' * 32}"
    assert decision.evidence_quote == "蓝色粗布短衫"
    assert [item.mapping_id for item in decision.mappings] == ["m1", "m2", "m3"]
    assert {item.semantic_unit_id for item in decision.mappings} == {"s1"}
    assert [item.field_path for item in decision.mappings] == [
        "clothing.color",
        "clothing.material",
        "clothing.type",
    ]
    assert all(item.evidence_quote == decision.evidence_quote for item in decision.mappings)


def test_m2_materializer_rejects_incomplete_or_duplicate_fact_indices() -> None:
    packet = _packet().model_copy(
        update={"grounded_facts": _packet().grounded_facts * 2},
    )
    output = FieldDisambiguationModelOutput.model_validate(_payload())
    with pytest.raises(ValueError, match="incomplete_field_disambiguation_fact_indices"):
        materialize_field_disambiguation_result(packet, output)


@pytest.mark.asyncio
async def test_m2_provider_reuses_structured_transport_and_records_metadata() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert f"gf_{'1' * 32}" not in body["messages"][1]["content"]
        return httpx.Response(
            200,
            headers={"x-request-id": "m2-request-1"},
            json={
                "model": "model-v1-revision",
                "choices": [{"message": {"content": json.dumps(_payload())}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 25},
            },
        )

    provider = OpenAICompatibleFieldDisambiguationProvider(
        provider="test-provider",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        max_retries=0,
        transport=httpx.MockTransport(respond),
    )
    detailed = await provider.disambiguate_detailed(_packet())
    assert detailed.output.schema_version == "field-disambiguation-result-v1"
    assert detailed.metadata.provider_request_id == "m2-request-1"
    assert detailed.metadata.usage.total_tokens == 65
    assert provider.version.endswith(
        ":field-disambiguation-model-wire-v1:field-disambiguation-result-v1:"
        "visual-field-catalog-v1:field-disambiguation-prompt-v1"
    )


def test_m2_runtime_prompt_documents_the_minimal_wire_and_string_policy() -> None:
    assert FIELD_DISAMBIGUATION_SYSTEM_PROMPT.startswith(
        "You decompose already-grounded character-visual propositions"
    )
    assert "Never return a fact ID or copy an evidence quote into the output." in (
        FIELD_DISAMBIGUATION_SYSTEM_PROMPT
    )
    assert "Do not return mapping IDs or semantic-unit IDs." in (
        FIELD_DISAMBIGUATION_SYSTEM_PROMPT
    )
    assert "Do not emit numbers, booleans, arrays, or enum codes." in (
        FIELD_DISAMBIGUATION_SYSTEM_PROMPT
    )
