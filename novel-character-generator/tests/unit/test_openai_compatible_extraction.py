import json

import httpx
import pytest

from novel_character_generator.infrastructure.llm.openai_compatible import (
    OpenAICompatibleExtractionProvider,
)


@pytest.mark.asyncio
async def test_openai_compatible_provider_requests_structured_json() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://llm.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["model"] == "model-v1"
        assert body["response_format"] == {"type": "json_object"}
        assert "沈砚黑发" in body["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "mentions": [],
                                    "alias_hypotheses": [],
                                    "observations": [],
                                    "expression_observations": [],
                                    "unresolved_references": [],
                                    "warnings": [],
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleExtractionProvider(
        provider="deepseek",
        base_url="https://llm.example/v1",
        api_key="secret",
        model="model-v1",
        transport=httpx.MockTransport(respond),
    )
    result = await provider.extract_chunk("沈砚黑发")
    assert result.mentions == []
    assert provider.version == "deepseek:model-v1"
