from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.domain.entities.document import (
    ChapterBoundary,
    NormalizedText,
    TextChunk,
)
from novel_character_generator.infrastructure.db.orm import (
    ChapterORM,
    NovelORM,
    PipelineRunORM,
    PipelineStepORM,
    SourceDocumentORM,
    TextChunkORM,
)


class IngestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_document_by_hash(self, sha256: str) -> SourceDocumentORM | None:
        return cast(
            SourceDocumentORM | None,
            await self.session.scalar(
                select(SourceDocumentORM).where(SourceDocumentORM.sha256 == sha256)
            ),
        )

    async def create_novel_and_document(
        self,
        *,
        title: str,
        sha256: str,
        encoding: str,
        storage_uri: str,
        byte_size: int,
    ) -> tuple[NovelORM, SourceDocumentORM]:
        now = datetime.now(UTC)
        novel = NovelORM(id=uuid4(), title=title, status="uploaded", created_at=now, updated_at=now)
        document = SourceDocumentORM(
            id=uuid4(),
            novel_id=novel.id,
            version=sha256,
            sha256=sha256,
            encoding=encoding,
            mime_type="text/plain",
            storage_uri=storage_uri,
            byte_size=byte_size,
            normalization_map_version=None,
            normalization_map=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add_all([novel, document])
        await self.session.flush()
        return novel, document

    async def get_novel(self, novel_id: UUID) -> NovelORM | None:
        return await self.session.get(NovelORM, novel_id)

    async def latest_document(self, novel_id: UUID) -> SourceDocumentORM | None:
        return cast(
            SourceDocumentORM | None,
            await self.session.scalar(
                select(SourceDocumentORM)
                .where(SourceDocumentORM.novel_id == novel_id)
                .order_by(SourceDocumentORM.created_at.desc())
            ),
        )

    async def get_run_by_idempotency_key(self, key: str) -> PipelineRunORM | None:
        return cast(
            PipelineRunORM | None,
            await self.session.scalar(
                select(PipelineRunORM).where(PipelineRunORM.idempotency_key == key)
            ),
        )

    async def create_import_run(
        self, novel_id: UUID, idempotency_key: str
    ) -> tuple[PipelineRunORM, PipelineStepORM]:
        now = datetime.now(UTC)
        run = PipelineRunORM(
            id=uuid4(),
            novel_id=novel_id,
            run_type="text_ingestion",
            status="queued",
            idempotency_key=idempotency_key,
            cancel_requested=False,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        step = PipelineStepORM(
            id=uuid4(),
            run_id=run.id,
            step_key="normalize_and_chunk",
            status="queued",
            attempt=0,
            lease_owner=None,
            lease_expires_at=None,
            lease_generation=0,
            heartbeat_at=None,
            next_attempt_at=None,
            cursor={"schema_version": "v1", "current_chunk_ordinal": 0},
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add_all([run, step])
        await self.session.flush()
        return run, step

    async def persist_processed_text(
        self,
        *,
        novel: NovelORM,
        document: SourceDocumentORM,
        normalized: NormalizedText,
        chapters: list[ChapterBoundary],
        chunks: list[TextChunk],
    ) -> None:
        await self.session.execute(delete(TextChunkORM).where(TextChunkORM.novel_id == novel.id))
        await self.session.execute(delete(ChapterORM).where(ChapterORM.novel_id == novel.id))
        chapter_ids: dict[int, UUID] = {}
        for chapter in chapters:
            original_start, original_end = normalized.original_span(
                chapter.normalized_start, chapter.normalized_end
            )
            chapter_id = uuid4()
            chapter_ids[chapter.ordinal] = chapter_id
            self.session.add(
                ChapterORM(
                    id=chapter_id,
                    novel_id=novel.id,
                    source_document_id=document.id,
                    ordinal=chapter.ordinal,
                    title=chapter.title,
                    original_char_start=original_start,
                    original_char_end=original_end,
                    normalized_char_start=chapter.normalized_start,
                    normalized_char_end=chapter.normalized_end,
                )
            )
        for chunk in chunks:
            self.session.add(
                TextChunkORM(
                    id=uuid4(),
                    novel_id=novel.id,
                    source_document_id=document.id,
                    chapter_id=chapter_ids[chunk.chapter_ordinal],
                    ordinal=chunk.ordinal,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    original_char_start=chunk.original_start,
                    original_char_end=chunk.original_end,
                    normalized_char_start=chunk.normalized_start,
                    normalized_char_end=chunk.normalized_end,
                )
            )
        document.normalization_map_version = normalized.map_version
        document.normalization_map = {"original_boundaries": normalized.original_boundaries}
        document.updated_at = datetime.now(UTC)
        novel.status = "chunked"
        novel.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def get_counts(self, novel_id: UUID) -> tuple[int, int]:
        chapters = await self.session.scalar(
            select(func.count()).select_from(ChapterORM).where(ChapterORM.novel_id == novel_id)
        )
        chunks = await self.session.scalar(
            select(func.count()).select_from(TextChunkORM).where(TextChunkORM.novel_id == novel_id)
        )
        return chapters or 0, chunks or 0
