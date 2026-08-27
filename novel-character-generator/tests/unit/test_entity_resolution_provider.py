from uuid import UUID

import httpx
import pytest

from novel_character_generator.application.ports.entity_resolution import (
    EntityResolutionInput,
    EntityResolutionResult,
)
from novel_character_generator.infrastructure.llm.entity_resolution import (
    RESOLUTION_SYSTEM_PROMPT,
    OpenAICompatibleEntityResolutionProvider,
)


def _request() -> EntityResolutionInput:
    return EntityResolutionInput(
        chunk_id=UUID(int=1),
        chunk_ordinal=0,
        chunk_text="唐三站在山顶。",
        candidates={"mentions": [], "facts": [], "temporal_signals": [], "warnings": []},
    )


def test_chat_completion_disables_reasoning_when_configured() -> None:
    provider = OpenAICompatibleEntityResolutionProvider(
        provider="deepseek",
        base_url="https://example.test/v1",
        api_key="secret",
        model="model-v1",
        thinking_enabled=False,
        reasoning_effort="none",
    )

    body = provider._body(RESOLUTION_SYSTEM_PROMPT, _request(), EntityResolutionResult)

    assert body["thinking"] == {"type": "disabled"}
    assert body["reasoning_effort"] == "none"
    assert provider.convergence_input_token_overhead > 0


def test_responses_api_uses_requested_reasoning_effort() -> None:
    provider = OpenAICompatibleEntityResolutionProvider(
        provider="openai_compatible",
        base_url="https://example.test/v1",
        api_key="secret",
        model="model-v1",
        wire_api="responses",
        reasoning_effort="low",
    )

    body = provider._body(RESOLUTION_SYSTEM_PROMPT, _request(), EntityResolutionResult)

    assert body["reasoning"] == {"effort": "low"}


@pytest.mark.asyncio
async def test_provider_retains_last_raw_response_for_development_capture() -> None:
    payload = {
        "id": "entity-response-1",
        "model": "model-v1-revision",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"decisions": []}'},
            }
        ],
    }

    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = OpenAICompatibleEntityResolutionProvider(
        provider="deepseek",
        base_url="https://example.test/v1",
        api_key="secret",
        model="model-v1",
        transport=httpx.MockTransport(respond),
    )

    result = await provider.resolve_chunk(_request())

    assert result.decisions == []
    assert provider.last_raw_message_content == '{"decisions": []}'
    assert provider.last_raw_response == payload
