import json

import httpx
import pytest

from novel_character_generator.application.ports.visual_evidence import (
    VisualEvidenceDiscoveryInput,
    VisualEvidenceExecutionRequest,
)
from novel_character_generator.application.services.visual_evidence_service import (
    VisualEvidenceShadowService,
)
from novel_character_generator.infrastructure.llm.visual_evidence import (
    OpenAICompatibleVisualEvidenceProvider,
)


@pytest.mark.asyncio
async def test_m1_v2_shadow_slice_is_immutable_and_reproducible() -> None:
    payload = {
        "mentions": [{"mention_quote": "沈砚"}],
        "evidence_candidates": [{"owner_index": 0, "evidence_quote": "黑色短发"}],
    }

    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-request-id": "m1-v2-1"},
            json={
                "model": "test-model-revision",
                "choices": [{"message": {"content": json.dumps(payload)}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6},
            },
        )

    provider = OpenAICompatibleVisualEvidenceProvider(
        provider="test-provider",
        base_url="https://llm.example/v1",
        api_key="test-secret",
        model="test-model",
        max_retries=0,
        transport=httpx.MockTransport(respond),
    )
    service = VisualEvidenceShadowService(provider)
    request = VisualEvidenceExecutionRequest(
        run_id="shadow-run-v2-1",
        source_document_version_id="source-v2",
        data_policy_version="m1-v2-shadow-data-v1",
        payload=VisualEvidenceDiscoveryInput(
            schema_version="visual-evidence-discovery-input-v2",
            chunk_id="chunk-7",
            chunk_text="沈砚留着黑色短发。",
            previous_tail=None,
        ),
    )

    first = await service.run(request)
    second = await service.run(request)

    assert first.node_id == "M1"
    assert first.contract_version == "visual-evidence-contract-v2"
    assert first.status == "succeeded"
    assert first.counts.mentions == 1
    assert first.counts.evidence_candidates == 1
    assert first.input_fingerprint == second.input_fingerprint
    assert first.output_fingerprint == second.output_fingerprint
    assert first.usage.usage.total_tokens == 18
