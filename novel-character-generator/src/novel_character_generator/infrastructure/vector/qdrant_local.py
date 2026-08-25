import asyncio
import re
from pathlib import Path
from uuid import UUID

from qdrant_client import QdrantClient, models

from novel_character_generator.application.ports.vector_store import (
    VectorPoint,
    VectorSearchHit,
    VectorStorePort,
)

_COLLECTION_TOKEN = re.compile(r"[^a-zA-Z0-9_]+")


def qdrant_collection_name(
    *, embedding_profile_version: str, dimension: int, index_version: str
) -> str:
    profile = _COLLECTION_TOKEN.sub("_", embedding_profile_version).strip("_")
    index = _COLLECTION_TOKEN.sub("_", index_version).strip("_")
    if not profile or not index:
        raise ValueError("invalid_qdrant_collection_component")
    return f"novel_passages__{profile}__d{dimension}__{index}"[:255]


class QdrantLocalVectorStore(VectorStorePort):
    def __init__(self, *, path: Path, collection_name: str, dimension: int) -> None:
        if dimension <= 0:
            raise ValueError("vector_dimension_must_be_positive")
        path.mkdir(parents=True, exist_ok=True)
        self._collection_name = collection_name
        self._dimension = dimension
        self._client = QdrantClient(path=str(path))

    @property
    def collection_name(self) -> str:
        return self._collection_name

    @property
    def dimension(self) -> int:
        return self._dimension

    async def ensure_collection(self) -> None:
        await asyncio.to_thread(self._ensure_collection_sync)

    def _ensure_collection_sync(self) -> None:
        if not self._client.collection_exists(self.collection_name):
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.dimension,
                    distance=models.Distance.COSINE,
                ),
            )
            return
        info = self._client.get_collection(self.collection_name)
        vector_config = info.config.params.vectors
        if not isinstance(vector_config, models.VectorParams):
            raise RuntimeError("qdrant_named_vector_configuration_not_supported")
        if vector_config.size != self.dimension:
            raise ValueError("qdrant_collection_dimension_mismatch")
        if vector_config.distance != models.Distance.COSINE:
            raise ValueError("qdrant_collection_distance_mismatch")

    async def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        for point in points:
            if len(point.vector) != self.dimension:
                raise ValueError("vector_dimension_mismatch")
        await asyncio.to_thread(self._upsert_sync, points)

    def _upsert_sync(self, points: list[VectorPoint]) -> None:
        self._client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(id=point.id, vector=point.vector, payload=point.payload)
                for point in points
            ],
            wait=True,
        )

    async def search(
        self,
        vector: list[float],
        *,
        retrieval_index_build_id: UUID,
        source_document_version_id: UUID,
        limit: int,
    ) -> list[VectorSearchHit]:
        if len(vector) != self.dimension:
            raise ValueError("vector_dimension_mismatch")
        if limit < 1:
            raise ValueError("vector_search_limit_must_be_positive")
        return await asyncio.to_thread(
            self._search_sync,
            vector,
            retrieval_index_build_id,
            source_document_version_id,
            limit,
        )

    def _search_sync(
        self,
        vector: list[float],
        retrieval_index_build_id: UUID,
        source_document_version_id: UUID,
        limit: int,
    ) -> list[VectorSearchHit]:
        response = self._client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="retrieval_index_build_id",
                        match=models.MatchValue(value=str(retrieval_index_build_id)),
                    ),
                    models.FieldCondition(
                        key="source_document_version_id",
                        match=models.MatchValue(value=str(source_document_version_id)),
                    ),
                ]
            ),
            limit=limit,
            with_payload=False,
            with_vectors=False,
        )
        return [
            VectorSearchHit(passage_id=UUID(str(point.id)), score=float(point.score))
            for point in response.points
        ]

    async def close(self) -> None:
        await asyncio.to_thread(self._client.close)
