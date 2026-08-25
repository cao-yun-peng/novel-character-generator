from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class VectorPoint:
    id: UUID
    vector: list[float]
    payload: dict[str, str | int]


@dataclass(frozen=True)
class VectorSearchHit:
    passage_id: UUID
    score: float


class VectorStorePort(Protocol):
    @property
    def collection_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def ensure_collection(self) -> None: ...

    async def upsert(self, points: list[VectorPoint]) -> None: ...

    async def search(
        self,
        vector: list[float],
        *,
        retrieval_index_build_id: UUID,
        source_document_version_id: UUID,
        limit: int,
    ) -> list[VectorSearchHit]: ...

    async def close(self) -> None: ...

