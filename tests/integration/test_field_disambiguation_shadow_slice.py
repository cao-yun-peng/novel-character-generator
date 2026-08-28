import json

import httpx
import pytest

from novel_character_generator.application.ports.field_disambiguation import (
    FieldDisambiguationExecutionRequest,
)
from novel_character_generator.application.ports.local_grounding import (
    GroundedEvidenceSpan,
    GroundedLocalFact,
    GroundedLocalPacket,
    GroundedMentionNode,
    LocalContextWindow,
)
from novel_character_generator.application.services.field_disambiguation_service import (
    FieldDisambiguationShadowService,
)
from novel_character_generator.infrastructure.llm.field_disambiguation import (
    OpenAICompatibleFieldDisambiguationProvider,
)


@pytest.mark.asyncio
async def test_n2_to_m2_shadow_slice_maps_without_persistence() -> None:
    packet = GroundedLocalPacket(
        schema_version="grounded-local-packet-v1",
        run_id="shadow-run-m2",
        source_document_version_id="source-v1",
        chunk_id="chunk-7",
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
                    quote_hash="7" * 64,
                ),
            ),
        ),
        grounded_facts=(
            GroundedLocalFact(
                fact_id=f"gf_{'3' * 32}",
                local_fact_id="f1",
                local_entity_id="e1",
                evidence_quote="碧绿的眼眸",
                evidence_span=GroundedEvidenceSpan(
                    start=2,
                    end=8,
                    source_quote="碧绿的眼眸",
                    quote_hash="f" * 64,
                ),
                grounding_status="exact",
                raw_proposition="她有碧绿的眼眸",
                coarse_family="face",
                epistemic_status="asserted",
                local_context=LocalContextWindow(
                    policy_version="local-context-sentence-window-v1",
                    start=0,
                    end=9,
                    text="她有碧绿的眼眸。",
                    focus_start=2,
                    focus_end=8,
                    context_hash="0" * 64,
                ),
            ),
        ),
        grounded_signals=(),
        rejected_items=(),
        deferred_items=(),
    )
    response = {
        "decisions": [
            {
                "fact_index": 0,
                "decision": "map",
                "mappings": [
                    {
                        "semantic_unit_index": 0,
                        "referent_kind": "body_part",
                        "referent_quote": "眼眸",
                        "field_path": "face.eye_color",
                        "normalized_value": "碧绿",
                    }
                ],
                "reason_code": "explicit_atomic_mapping",
            }
        ]
    }

    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(response)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    provider = OpenAICompatibleFieldDisambiguationProvider(
        provider="test-provider",
        base_url="https://llm.example/v1",
        api_key="test-secret",
        model="test-model",
        max_retries=0,
        transport=httpx.MockTransport(respond),
    )
    artifact = await FieldDisambiguationShadowService(provider).run(
        FieldDisambiguationExecutionRequest(
            schema_version="field-disambiguation-input-v1",
            data_policy_version="m2-shadow-data-v1",
            grounded_packet=packet,
        )
    )
    mapping = artifact.output.decisions[0].mappings[0]
    assert artifact.node_id == "M2"
    assert artifact.status == "succeeded"
    assert mapping.field_path == "face.eye_color"
    assert mapping.normalized_value == "碧绿"
    assert mapping.mapping_id == "m1"
    assert mapping.semantic_unit_id == "s1"
    assert mapping.evidence_quote == "碧绿的眼眸"
    assert artifact.usage.usage.total_tokens == 30
