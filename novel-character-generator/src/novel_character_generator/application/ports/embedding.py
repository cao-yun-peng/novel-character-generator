from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str
    model: str
    model_revision: str | None
    dimension: int
    profile_version: str
    normalization: Literal["none", "l2"]
    document_prefix: str = ""
    query_prefix: str = ""


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    input_tokens: int | None = None


class EmbeddingPort(Protocol):
    @property
    def profile(self) -> EmbeddingProfile: ...

    async def embed_documents(self, texts: list[str]) -> EmbeddingBatch: ...

    async def embed_queries(self, texts: list[str]) -> EmbeddingBatch: ...

    async def close(self) -> None: ...

