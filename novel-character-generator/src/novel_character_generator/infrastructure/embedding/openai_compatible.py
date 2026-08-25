import asyncio
import math
from collections.abc import Sequence

import httpx

from novel_character_generator.application.ports.embedding import (
    EmbeddingBatch,
    EmbeddingPort,
    EmbeddingProfile,
)


class OpenAICompatibleEmbeddingProvider(EmbeddingPort):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        profile: EmbeddingProfile,
        timeout_seconds: float = 60,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._profile = profile
        self._max_retries = max_retries
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    async def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        return await self._embed(texts, prefix=self.profile.document_prefix)

    async def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        return await self._embed(texts, prefix=self.profile.query_prefix)

    async def _embed(self, texts: list[str], *, prefix: str) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(vectors=[])
        inputs = [f"{prefix}{text}" for text in texts]
        response: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            response = await self._client.post(
                "/embeddings",
                json={"model": self.profile.model, "input": inputs},
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            if attempt == self._max_retries:
                break
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else min(8.0, float(2**attempt))
            await asyncio.sleep(max(0.0, delay))
        assert response is not None
        response.raise_for_status()
        payload = response.json()
        raw_data = payload.get("data")
        if not isinstance(raw_data, list) or len(raw_data) != len(inputs):
            raise ValueError("embedding_response_count_mismatch")
        ordered: list[list[float] | None] = [None] * len(inputs)
        for fallback_index, item in enumerate(raw_data):
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise ValueError("embedding_response_invalid")
            index = item.get("index", fallback_index)
            if not isinstance(index, int) or not 0 <= index < len(inputs):
                raise ValueError("embedding_response_index_invalid")
            vector = [float(value) for value in item["embedding"]]
            ordered[index] = self._validate_and_normalize(vector)
        if any(vector is None for vector in ordered):
            raise ValueError("embedding_response_missing_vector")
        usage = payload.get("usage")
        input_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        return EmbeddingBatch(
            vectors=[vector for vector in ordered if vector is not None],
            input_tokens=input_tokens if isinstance(input_tokens, int) else None,
        )

    def _validate_and_normalize(self, vector: Sequence[float]) -> list[float]:
        if len(vector) != self.profile.dimension:
            raise ValueError("embedding_dimension_mismatch")
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("embedding_vector_non_finite")
        if self.profile.normalization == "none":
            return list(vector)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise ValueError("embedding_zero_vector")
        return [value / norm for value in vector]

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

