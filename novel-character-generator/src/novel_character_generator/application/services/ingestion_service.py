import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.artifact_store import ArtifactStore
from novel_character_generator.application.services.retrieval_indexing_service import (
    RetrievalIndexingService,
)
from novel_character_generator.domain.policies.text_processing import decode_text
from novel_character_generator.infrastructure.db.orm import (
    NovelORM,
    PipelineRunORM,
    RetrievalIndexBuildORM,
    SourceDocumentVersionORM,
)
from novel_character_generator.infrastructure.db.repositories.ingestion import IngestionRepository
from novel_character_generator.infrastructure.db.repositories.retrieval import RetrievalRepository
from novel_character_generator.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NovelDetails:
    id: UUID
    title: str
    status: str
    source_sha256: str
    chapter_count: int
    chunk_count: int
    retrieval_index_build_id: UUID | None
    retrieval_index_status: str | None
    retrieval_passage_count: int


class IngestionService:
    def __init__(self, session: AsyncSession, artifact_store: ArtifactStore) -> None:
        self.session = session
        self.artifact_store = artifact_store
        self.repository = IngestionRepository(session)

    async def list_novels(self, *, limit: int = 50) -> list[NovelORM]:
        return await self.repository.list_novels(limit=limit)

    async def list_runs(
        self, novel_id: UUID, *, limit: int = 20
    ) -> list[PipelineRunORM] | None:
        if await self.repository.get_novel(novel_id) is None:
            return None
        return await self.repository.list_runs(novel_id, limit=limit)

    async def upload(self, *, filename: str, data: bytes) -> NovelORM:
        text, encoding = decode_text(data)
        if not text.strip():
            raise ValueError("empty_text_file")
        sha256 = hashlib.sha256(data).hexdigest()
        existing = await self.repository.find_document_by_hash(sha256)
        if existing is not None:
            document = await self.repository.get_document(existing.source_document_id)
            novel = (
                await self.repository.get_novel(document.novel_id) if document is not None else None
            )
            if novel is None:
                raise RuntimeError("source_document_without_novel")
            await RetrievalIndexingService(self.session, get_settings()).ensure_run(
                novel_id=novel.id,
                source_document_version_id=existing.id,
            )
            await self.session.commit()
            return novel
        storage_uri = await self.artifact_store.put(content_hash=sha256, data=data)
        title = Path(filename).stem.strip() or "Untitled"
        novel, _, document_version = await self.repository.create_novel_and_document(
            title=title,
            sha256=sha256,
            encoding=encoding,
            storage_uri=storage_uri,
            byte_size=len(data),
        )
        await RetrievalIndexingService(self.session, get_settings()).ensure_run(
            novel_id=novel.id,
            source_document_version_id=document_version.id,
        )
        await self.session.commit()
        return novel

    async def upload_version(
        self, *, novel_id: UUID, filename: str, data: bytes
    ) -> SourceDocumentVersionORM | None:
        del filename  # The logical document keeps its original user-facing title.
        text, encoding = decode_text(data)
        if not text.strip():
            raise ValueError("empty_text_file")
        novel = await self.repository.get_novel(novel_id)
        if novel is None:
            return None
        document = await self.repository.latest_document(novel_id)
        if document is None:
            raise RuntimeError("novel_without_source_document")
        sha256 = hashlib.sha256(data).hexdigest()
        storage_uri = await self.artifact_store.put(content_hash=sha256, data=data)
        previous_version_id = document.current_version_id
        previous_version = (
            await self.session.get(SourceDocumentVersionORM, previous_version_id)
            if previous_version_id is not None
            else None
        )
        document_version = await self.repository.create_document_version(
            document=document,
            sha256=sha256,
            encoding=encoding,
            storage_uri=storage_uri,
            byte_size=len(data),
        )
        await RetrievalIndexingService(self.session, get_settings()).ensure_run(
            novel_id=novel.id,
            source_document_version_id=document_version.id,
        )
        novel.status = "uploaded"
        await self.session.commit()
        if previous_version_id is not None and previous_version_id != document_version.id:
            logger.info(
                "generation.dependency.invalidated",
                extra={
                    "event_name": "generation.dependency.invalidated",
                    "novel_id": str(novel_id),
                    "old_source_document_version_id": str(previous_version_id),
                    "new_source_document_version_id": str(document_version.id),
                    "old_hash": previous_version.content_sha256 if previous_version else None,
                    "new_hash": document_version.content_sha256,
                    "affected_snapshot_count": 0,
                    "affected_image_count": 0,
                    "affected_dependency_types": [
                        "feature_observation",
                        "appearance_state",
                        "render_profile",
                        "character_conflict",
                    ],
                },
            )
        return document_version

    async def details(self, novel_id: UUID) -> NovelDetails | None:
        novel = await self.repository.get_novel(novel_id)
        if novel is None:
            return None
        document_version = await self.repository.latest_document_version(novel_id)
        if document_version is None:
            raise RuntimeError("novel_without_source_document")
        chapter_count, chunk_count = await self.repository.get_counts(novel_id)
        retrieval_repository = RetrievalRepository(self.session)
        retrieval_build = await retrieval_repository.latest_build_for_source(document_version.id)
        retrieval_passage_count = (
            await retrieval_repository.count_passages(retrieval_build.id)
            if retrieval_build is not None
            else 0
        )
        return NovelDetails(
            id=novel.id,
            title=novel.title,
            status=novel.status,
            source_sha256=document_version.content_sha256,
            chapter_count=chapter_count,
            chunk_count=chunk_count,
            retrieval_index_build_id=retrieval_build.id if retrieval_build else None,
            retrieval_index_status=retrieval_build.status if retrieval_build else None,
            retrieval_passage_count=retrieval_passage_count,
        )

    async def ensure_retrieval_index(
        self, novel_id: UUID
    ) -> tuple[RetrievalIndexBuildORM, PipelineRunORM] | None:
        if await self.repository.get_novel(novel_id) is None:
            return None
        document_version = await self.repository.latest_document_version(novel_id)
        if document_version is None:
            raise RuntimeError("novel_without_source_document")
        build, run = await RetrievalIndexingService(self.session, get_settings()).ensure_run(
            novel_id=novel_id,
            source_document_version_id=document_version.id,
        )
        await self.session.commit()
        return build, run

    async def create_run(self, novel_id: UUID, idempotency_key: str) -> PipelineRunORM | None:
        if await self.repository.get_novel(novel_id) is None:
            return None
        existing = await self.repository.get_run_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.novel_id != novel_id or existing.run_type != "text_ingestion":
                raise ValueError("idempotency_key_conflict")
            return existing
        run, _ = await self.repository.create_import_run(novel_id, idempotency_key)
        await self.session.commit()
        return run

    async def create_extraction_run(
        self, novel_id: UUID, idempotency_key: str
    ) -> PipelineRunORM | None:
        novel = await self.repository.get_novel(novel_id)
        if novel is None:
            return None
        if novel.status != "chunked":
            raise ValueError("novel_not_chunked")
        existing = await self.repository.get_run_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.novel_id != novel_id or existing.run_type != "character_extraction":
                raise ValueError("idempotency_key_conflict")
            return existing
        run, _ = await self.repository.create_extraction_run(novel_id, idempotency_key)
        await self.session.commit()
        return run

    async def create_analysis_run(
        self, novel_id: UUID, idempotency_key: str
    ) -> PipelineRunORM | None:
        if await self.repository.get_novel(novel_id) is None:
            return None
        existing = await self.repository.get_run_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.novel_id != novel_id or existing.run_type != "text_analysis":
                raise ValueError("idempotency_key_conflict")
            return existing
        run, _ = await self.repository.create_analysis_run(novel_id, idempotency_key)
        await self.session.commit()
        return run
