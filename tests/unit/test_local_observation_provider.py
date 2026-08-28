import json

import httpx
import pytest

from novel_character_generator.application.ports.local_observation import (
    DEFAULT_COARSE_VISUAL_FAMILIES,
    LocalObservationDiscoveryInput,
    LocalObservationModelOutput,
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
        "entities": [
            {
                "mention_quote": "沈砚",
                "mention_kind": "explicit_name",
            }
        ],
        "facts": [
            {
                "owner_index": 0,
                "evidence_quote": "黑色短发",
                "raw_proposition": "沈砚留着黑色短发",
                "coarse_family": "hair",
                "epistemic_status": "asserted",
            }
        ],
        "temporal_signals": [],
        "unresolved_items": [],
    }


def test_m1_request_contains_only_chunk_and_minimal_model_schema() -> None:
    body = build_local_observation_request(_request(), model="model-v1")
    serialized = json.dumps(body, ensure_ascii=False)
    user_content = body["messages"][1]["content"]
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0
    assert "沈砚留着黑色短发。" in user_content
    assert "chunk-1" not in user_content
    assert "previous_tail" not in user_content
    assert "allowed_coarse_families" not in user_content
    assert "schema_version" not in user_content
    assert "local_entity_id" not in user_content
    assert "entity_ref" not in user_content
    assert "representative_name" not in user_content
    assert "owner_index" in user_content
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
    assert body["text"]["format"]["schema"]["title"] == ("LocalObservationModelOutput")
    assert "LocalObservationModelOutput" not in body["input"]
    assert "chunk-1" not in body["input"]


def test_m1_wire_schema_excludes_code_generated_fields() -> None:
    rendered = json.dumps(LocalObservationModelOutput.model_json_schema())
    for field in (
        "schema_version",
        "chunk_id",
        "local_entity_id",
        "local_fact_id",
        "local_signal_id",
        "local_item_id",
        "representative_name",
        "raw_label",
        "entity_ref",
        "fact_ref",
    ):
        assert field not in rendered


def test_runtime_prompt_is_single_packaged_source() -> None:
    assert LOCAL_OBSERVATION_SYSTEM_PROMPT.startswith(
        "You discover source-backed, chunk-local character observation units"
    )
    assert "Do not duplicate a fact in both facts and unresolved_items." in (
        LOCAL_OBSERVATION_SYSTEM_PROMPT
    )
    assert "AGE FACTS AND AGE SIGNALS" in LOCAL_OBSERVATION_SYSTEM_PROMPT
    assert "never to a nearby hair, face, body, or clothing fact" in (
        LOCAL_OBSERVATION_SYSTEM_PROMPT
    )
    assert "Quote the appearance-changing action" in LOCAL_OBSERVATION_SYSTEM_PROMPT
    assert "must be omitted, not converted into unresolved items" in (
        LOCAL_OBSERVATION_SYSTEM_PROMPT
    )


@pytest.mark.asyncio
async def test_m1_provider_reuses_structured_transport_and_records_metadata() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://llm.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert "chunk-1" not in body["messages"][1]["content"]
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
    assert detailed.output.schema_version == "local-observation-discovery-v1.1"
    assert detailed.output.chunk_id == "chunk-1"
    assert detailed.output.entities[0].local_entity_id == "e1"
    assert detailed.output.entities[0].representative_name == "沈砚"
    assert detailed.output.facts[0].local_fact_id == "f1"
    assert detailed.output.facts[0].entity_ref == "e1"
    assert detailed.output.facts[0].raw_proposition == "沈砚留着黑色短发"
    assert detailed.metadata.provider_request_id == "m1-request-1"
    assert detailed.metadata.usage.total_tokens == 50
    assert provider.version.endswith(
        ":local-observation-model-wire-v1:local-observation-discovery-v1.1:"
        "local-observation-discovery-prompt-v1.6"
    )
    assert len(provider.prompt_hash) == 64


@pytest.mark.asyncio
async def test_m1_provider_retries_incomplete_schema_once() -> None:
    calls = 0

    async def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = {"entities": []} if calls == 1 else _result_payload()
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


@pytest.mark.asyncio
async def test_m1_provider_materializes_signal_indices_and_labels() -> None:
    payload = _result_payload()
    payload["entities"].insert(  # type: ignore[union-attr]
        0,
        {"mention_quote": "旁人", "mention_kind": "descriptor"},
    )
    payload["facts"][0]["owner_index"] = 1  # type: ignore[index]
    payload["temporal_signals"] = [
        {
            "owner_index": 1,
            "fact_index": None,
            "evidence_quote": "黑色短发",
            "signal_kind": "presentation",
        },
        {
            "owner_index": 1,
            "fact_index": None,
            "evidence_quote": "换了装束",
            "signal_kind": "presentation",
        },
    ]

    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )

    provider = OpenAICompatibleLocalObservationProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        max_retries=0,
        transport=httpx.MockTransport(respond),
    )
    detailed = await provider.discover_detailed(_request())

    linked, owner_only = detailed.output.temporal_signals
    assert len(detailed.output.entities) == 1
    assert detailed.output.entities[0].mention_quote == "沈砚"
    assert (linked.local_signal_id, linked.entity_ref, linked.fact_ref) == (
        "t1",
        "e1",
        "f1",
    )
    assert linked.raw_label == linked.evidence_quote
    assert (owner_only.local_signal_id, owner_only.entity_ref, owner_only.fact_ref) == (
        "t2",
        "e1",
        None,
    )
