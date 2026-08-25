from pathlib import Path
from uuid import uuid4

import pytest

from novel_character_generator.application.ports.vector_store import VectorPoint
from novel_character_generator.infrastructure.vector.qdrant_local import (
    QdrantLocalVectorStore,
    qdrant_collection_name,
)


@pytest.mark.asyncio
async def test_qdrant_local_persists_filters_and_rejects_dimension_mismatch(
    tmp_path: Path,
) -> None:
    collection = qdrant_collection_name(
        embedding_profile_version="zh/embed-v1",
        dimension=3,
        index_version="retrieval-v2",
    )
    build_id = uuid4()
    source_id = uuid4()
    other_build_id = uuid4()
    first_id = uuid4()
    store = QdrantLocalVectorStore(
        path=tmp_path / "qdrant",
        collection_name=collection,
        dimension=3,
    )
    await store.ensure_collection()
    await store.upsert(
        [
            VectorPoint(
                id=first_id,
                vector=[1, 0, 0],
                payload={
                    "retrieval_index_build_id": str(build_id),
                    "source_document_version_id": str(source_id),
                },
            ),
            VectorPoint(
                id=uuid4(),
                vector=[1, 0, 0],
                payload={
                    "retrieval_index_build_id": str(other_build_id),
                    "source_document_version_id": str(source_id),
                },
            ),
        ]
    )
    hits = await store.search(
        [1, 0, 0],
        retrieval_index_build_id=build_id,
        source_document_version_id=source_id,
        limit=10,
    )
    assert [hit.passage_id for hit in hits] == [first_id]
    await store.close()

    reopened = QdrantLocalVectorStore(
        path=tmp_path / "qdrant",
        collection_name=collection,
        dimension=3,
    )
    await reopened.ensure_collection()
    repeated = await reopened.search(
        [1, 0, 0],
        retrieval_index_build_id=build_id,
        source_document_version_id=source_id,
        limit=10,
    )
    assert [hit.passage_id for hit in repeated] == [first_id]
    await reopened.close()

    mismatched = QdrantLocalVectorStore(
        path=tmp_path / "qdrant",
        collection_name=collection,
        dimension=4,
    )
    with pytest.raises(ValueError, match="qdrant_collection_dimension_mismatch"):
        await mismatched.ensure_collection()
    await mismatched.close()
