import json

import httpx
import pytest
import respx

from novel_character_generator.application.ports.embedding import EmbeddingProfile
from novel_character_generator.infrastructure.embedding.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)


def _profile(*, dimension: int = 3) -> EmbeddingProfile:
    return EmbeddingProfile(
        provider="openai_compatible",
        model="embed-test",
        model_revision="r1",
        dimension=dimension,
        profile_version="embed-test-v1",
        normalization="l2",
        document_prefix="passage: ",
        query_prefix="query: ",
    )


@pytest.mark.asyncio
@respx.mock
async def test_embedding_provider_batches_retries_and_normalizes() -> None:
    route = respx.post("https://embedding.test/v1/embeddings").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(503, headers={"Retry-After": "0"}),
            httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": [0, 3, 4]},
                        {"index": 0, "embedding": [3, 0, 4]},
                    ],
                    "usage": {"prompt_tokens": 12},
                },
            ),
        ]
    )
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://embedding.test/v1",
        api_key="secret-not-logged",
        profile=_profile(),
        max_retries=2,
    )

    result = await provider.embed_documents(["甲", "乙"])

    assert route.call_count == 3
    assert route.calls[-1].request.headers["Authorization"] == "Bearer secret-not-logged"
    assert json.loads(route.calls[-1].request.content) == {
        "model": "embed-test",
        "input": ["passage: 甲", "passage: 乙"],
    }
    assert result.vectors == [[0.6, 0.0, 0.8], [0.0, 0.6, 0.8]]
    assert result.input_tokens == 12
    await provider.close()


@pytest.mark.asyncio
@respx.mock
async def test_embedding_provider_rejects_dimension_mismatch() -> None:
    respx.post("https://embedding.test/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [1, 2]}]},
        )
    )
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://embedding.test",
        api_key="secret",
        profile=_profile(dimension=3),
    )

    with pytest.raises(ValueError, match="embedding_dimension_mismatch"):
        await provider.embed_queries(["query"])
    await provider.close()
