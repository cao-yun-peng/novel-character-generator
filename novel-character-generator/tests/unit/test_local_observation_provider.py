import json

import httpx
import pytest

from novel_character_generator.application.ports.local_observation import (
    DEFAULT_COARSE_VISUAL_FAMILIES,
    LocalObservationDiscoveryInput,
)
from novel_character_generator.infrastructure.llm.local_observation import (
    LOCAL_OBSERVATION_SYSTEM_PROMPT,
    OpenAICompatibleLocalObservationProvider,
    build_local_observation_request,
)


def _request() -> LocalObservationDiscoveryInput:
    return LocalObservationDiscoveryInput(
        schema_version="local-observation-discovery-input-v1.1",
        chunk_id="chunk-1",
        chunk_text="沈砚留着黑色短发。",
        previous_tail=None,
        allowed_coarse_families=list(DEFAULT_COARSE_VISUAL_FAMILIES),
    )


def _result_payload() -> dict[str, object]:
    return {
        "schema_version": "local-observation-discovery-v1.1",
        "chunk_id": "chunk-1",
        "entities": [
            {
                "local_entity_id": "e1",
                "mention_quote": "沈砚",
                "mention_kind": "explicit_name",
                "representative_name": "沈砚",
            }
        ],
        "facts": [
            {
                "local_fact_id": "f1",
                "entity_ref": "e1",
                "evidence_quote": "黑色短发",
                "raw_proposition": "沈砚留着黑色短发",
                "coarse_family": "hair",
                "epistemic_status": "asserted",
            }
        ],
        "temporal_signals": [],
        "unresolved_items": [],
    }


def test_m1_request_contains_exact_input_and_strict_output_schema() -> None:
    body = build_local_observation_request(_request(), model="model-v1")
    serialized = json.dumps(body, ensure_ascii=False)
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0
    assert '"chunk_id":"chunk-1"' in body["messages"][1]["content"]
    assert "raw_proposition" in serialized
    assert "field_path" not in serialized
    assert "confidence" not in body["messages"][1]["content"]
    assert "confidence scores" in body["messages"][0]["content"]
    assert "cross-chunk identity resolution" in body["messages"][0]["content"]
    assert "api_key" not in serialized


def test_m1_responses_request_uses_json_schema_mode() -> None:
    body = build_local_observation_request(
        _request(),
        model="model-v1",
        wire_api="responses",
        reasoning_effort="low",
        max_output_tokens=4_096,
    )
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_output_tokens"] == 4_096
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["schema"]["title"] == (
        "LocalObservationDiscoveryResult"
    )


def test_runtime_prompt_is_single_packaged_source() -> None:
    assert LOCAL_OBSERVATION_SYSTEM_PROMPT.startswith(
        "You discover source-backed, chunk-local character observation units"
    )
    assert "Do not duplicate a fact in both facts and unresolved_items." in (
        LOCAL_OBSERVATION_SYSTEM_PROMPT
    )


@pytest.mark.asyncio
async def test_m1_provider_reuses_structured_transport_and_records_metadata() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://llm.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert '"chunk_id":"chunk-1"' in body["messages"][1]["content"]
        return httpx.Response(
            200,
            headers={"x-request-id": "m1-request-1"},
            json={
                "model": "model-v1-revision",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(_result_payload())},
                    }
                ],
                "usage": {"prompt_tokens": 30, "completion_tokens": 20},
            },
        )

    provider = OpenAICompatibleLocalObservationProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        transport=httpx.MockTransport(respond),
    )
    detailed = await provider.discover_detailed(_request())
    assert detailed.output.facts[0].raw_proposition == "沈砚留着黑色短发"
    assert detailed.metadata.provider_request_id == "m1-request-1"
    assert detailed.metadata.usage.total_tokens == 50
    assert provider.version.endswith(
        ":local-observation-discovery-v1.1:local-observation-discovery-prompt-v1.1"
    )
    assert len(provider.prompt_hash) == 64


@pytest.mark.asyncio
async def test_m1_provider_retries_incomplete_schema_once() -> None:
    calls = 0

    async def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = {"chunk_id": "chunk-1"} if calls == 1 else _result_payload()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )

    provider = OpenAICompatibleLocalObservationProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        max_retries=1,
        transport=httpx.MockTransport(respond),
    )
    detailed = await provider.discover_detailed(_request())
    assert calls == 2
    assert detailed.metadata.attempts == 2
