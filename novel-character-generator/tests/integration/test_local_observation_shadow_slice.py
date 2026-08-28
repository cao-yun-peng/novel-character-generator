import json

import httpx
import pytest

from novel_character_generator.application.ports.local_observation import (
    DEFAULT_COARSE_VISUAL_FAMILIES,
    LocalObservationDiscoveryInput,
    LocalObservationExecutionRequest,
)
from novel_character_generator.application.services.local_observation_service import (
    LocalObservationShadowService,
)
from novel_character_generator.infrastructure.llm.local_observation import (
    OpenAICompatibleLocalObservationProvider,
)


@pytest.mark.asyncio
async def test_m1_shadow_slice_returns_reproducible_artifact_without_persistence() -> None:
    output = {
        "schema_version": "local-observation-discovery-v1.1",
        "chunk_id": "chunk-7",
        "entities": [],
        "facts": [],
        "temporal_signals": [],
        "unresolved_items": [],
    }

    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(output)}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6},
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
    service = LocalObservationShadowService(provider)
    request = LocalObservationExecutionRequest(
        run_id="shadow-run-1",
        source_document_version_id="source-v1",
        data_policy_version="m1-shadow-data-v1",
        payload=LocalObservationDiscoveryInput(
            schema_version="local-observation-discovery-input-v1.1",
            chunk_id="chunk-7",
            chunk_text="天色已晚，众人继续赶路。",
            previous_tail=None,
            allowed_coarse_families=list(DEFAULT_COARSE_VISUAL_FAMILIES),
        ),
    )

    first = await service.run(request)
    second = await service.run(request)

    assert first.node_id == "M1"
    assert first.status == "completed_with_warnings"
    assert first.reason_codes == ("empty_discovery",)
    assert first.counts.facts == 0
    assert first.input_fingerprint == second.input_fingerprint
    assert first.output_fingerprint == second.output_fingerprint
    assert first.usage.usage.total_tokens == 18
