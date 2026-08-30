from __future__ import annotations

import json

import httpx
import pytest

from novel_character_generator.application.ports.evidence_grounding import (
    EvidenceGroundingExecutionRequest,
)
from novel_character_generator.application.ports.visual_evidence import (
    VisualEvidenceDiscoveryInput,
    VisualEvidenceExecutionRequest,
)
from novel_character_generator.application.services.evidence_grounding_service import (
    EvidenceGroundingService,
)
from novel_character_generator.application.services.visual_evidence_service import (
    VisualEvidenceShadowService,
)
from novel_character_generator.infrastructure.llm.visual_evidence import (
    OpenAICompatibleVisualEvidenceProvider,
)


@pytest.mark.asyncio
async def test_m1_v2_output_flows_into_n2_v2_without_persistence() -> None:
    chunk_text = "男子年龄在二十左右，英俊的相貌，配上挺拔的身材。"
    model_output = {
        "mentions": [{"mention_quote": "男子"}],
        "evidence_candidates": [
            {
                "owner_index": 0,
                "evidence_quote": "男子年龄在二十左右，英俊的相貌，配上挺拔的身材",
            }
        ],
    }

    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(model_output)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 12},
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
    m1 = await VisualEvidenceShadowService(provider).run(
        VisualEvidenceExecutionRequest(
            run_id="shadow-run-v2",
            source_document_version_id="source-v1",
            data_policy_version="shadow-data-v1",
            payload=VisualEvidenceDiscoveryInput(
                schema_version="visual-evidence-discovery-input-v2",
                chunk_id="chunk-7",
                chunk_text=chunk_text,
            ),
        )
    )
    n2 = EvidenceGroundingService().ground(
        EvidenceGroundingExecutionRequest(
            schema_version="evidence-grounding-input-v2",
            run_id=m1.run_id,
            source_document_version_id=m1.source_document_version_id,
            chunk_id=m1.chunk_id,
            chunk_text=chunk_text,
            discovery=m1.output,
        )
    )

    assert n2.node_id == "N2"
    assert n2.status == "succeeded"
    assert n2.counts.grounded_candidates == 1
    assert n2.output.grounded_candidates[0].local_owner_id == "m1"
    assert n2.output.grounded_candidates[0].local_context.text == chunk_text
