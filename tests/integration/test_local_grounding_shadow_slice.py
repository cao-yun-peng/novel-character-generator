from __future__ import annotations

import json

import httpx
import pytest

from novel_character_generator.application.ports.local_grounding import (
    LocalGroundingExecutionRequest,
)
from novel_character_generator.application.ports.local_observation import (
    DEFAULT_COARSE_VISUAL_FAMILIES,
    LocalObservationDiscoveryInput,
    LocalObservationExecutionRequest,
)
from novel_character_generator.application.services.local_grounding_service import (
    LocalGroundingService,
)
from novel_character_generator.application.services.local_observation_service import (
    LocalObservationShadowService,
)
from novel_character_generator.infrastructure.llm.local_observation import (
    OpenAICompatibleLocalObservationProvider,
)


@pytest.mark.asyncio
async def test_m1_output_flows_through_n2_without_persistence() -> None:
    chunk_text = "男子年龄在二十左右，英俊的相貌，配上挺拔的身材。"
    model_output = {
        "entities": [
            {
                "mention_quote": "男子",
                "mention_kind": "descriptor",
            }
        ],
        "facts": [
            {
                "owner_index": 0,
                "evidence_quote": "男子年龄在二十左右，英俊的相貌，配上挺拔的身材",
                "raw_proposition": "男子年龄二十左右、相貌英俊、身材挺拔。",
                "coarse_family": "physical_identity",
                "epistemic_status": "asserted",
            }
        ],
        "temporal_signals": [
            {
                "fact_index": 0,
                "evidence_quote": "男子年龄在二十左右",
                "signal_kind": "age",
            }
        ],
        "unresolved_items": [],
    }

    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(model_output)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 12},
            },
        )

    provider = OpenAICompatibleLocalObservationProvider(
        provider="test-provider",
        base_url="https://llm.example/v1",
        api_key="test-secret",
        model="test-model",
        max_retries=0,
        transport=httpx.MockTransport(respond),
    )
    m1_request = LocalObservationExecutionRequest(
        run_id="shadow-run-1",
        source_document_version_id="source-v1",
        data_policy_version="m1-shadow-data-v1",
        payload=LocalObservationDiscoveryInput(
            schema_version="local-observation-discovery-input-v1.1",
            chunk_id="chunk-7",
            chunk_text=chunk_text,
            previous_tail=None,
            allowed_coarse_families=list(DEFAULT_COARSE_VISUAL_FAMILIES),
        ),
    )

    m1_artifact = await LocalObservationShadowService(provider).run(m1_request)
    n2_artifact = LocalGroundingService().ground(
        LocalGroundingExecutionRequest(
            schema_version="local-grounding-input-v1",
            run_id=m1_artifact.run_id,
            source_document_version_id=m1_artifact.source_document_version_id,
            chunk_id=m1_artifact.chunk_id,
            chunk_text=chunk_text,
            discovery=m1_artifact.output,
        )
    )

    assert n2_artifact.node_id == "N2"
    assert n2_artifact.status == "succeeded"
    assert n2_artifact.counts.grounded_facts == 1
    assert n2_artifact.counts.grounded_signals == 1
    assert n2_artifact.output.grounded_signals[0].grounded_fact_id == (
        n2_artifact.output.grounded_facts[0].fact_id
    )
    assert n2_artifact.output.grounded_facts[0].local_context.text == chunk_text
