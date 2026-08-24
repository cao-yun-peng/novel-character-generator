from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.domain.entities.document import (
    ChapterBoundary,
    NormalizedText,
    TextChunk,
)
from novel_character_generator.infrastructure.db.orm import (
    ChapterORM,
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterORM,
    CharacterRenderProfileORM,
    FeatureObservationORM,
    NormalizationMapORM,
    NovelORM,
    PipelineRunORM,
    PipelineStepORM,
    SourceDocumentORM,
    SourceDocumentVersionORM,
    TextChunkORM,
)
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event


class IngestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_document_by_hash(self, sha256: str) -> SourceDocumentVersionORM | None:
        return cast(
            SourceDocumentVersionORM | None,
            await self.session.scalar(
                select(SourceDocumentVersionORM).where(
                    SourceDocumentVersionORM.content_sha256 == sha256
                )
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
    ) -> tuple[NovelORM, SourceDocumentORM, SourceDocumentVersionORM]:
        now = datetime.now(UTC)
        novel = NovelORM(id=uuid4(), title=title, status="uploaded", created_at=now, updated_at=now)
        document = SourceDocumentORM(
            id=uuid4(),
            novel_id=novel.id,
            current_version_id=None,
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
        document_version = SourceDocumentVersionORM(
            id=uuid4(),
            source_document_id=document.id,
            version=1,
            content_sha256=sha256,
            encoding=encoding,
            mime_type="text/plain",
            storage_uri=storage_uri,
            byte_size=byte_size,
            normalization_map_id=None,
            supersedes_version_id=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(document_version)
        await self.session.flush()
        document.current_version_id = document_version.id
        await self.session.flush()
        return novel, document, document_version

    async def create_document_version(
        self,
        *,
        document: SourceDocumentORM,
        sha256: str,
        encoding: str,
        storage_uri: str,
        byte_size: int,
    ) -> SourceDocumentVersionORM:
        current = (
            await self.session.get(SourceDocumentVersionORM, document.current_version_id)
            if document.current_version_id is not None
            else None
        )
        if current is not None and current.content_sha256 == sha256:
            return current
        now = datetime.now(UTC)
        if current is not None:
            await self.invalidate_source_version_dependencies(
                novel_id=document.novel_id,
                source_document_version_id=current.id,
                invalidated_at=now,
            )
        document_version = SourceDocumentVersionORM(
            id=uuid4(),
            source_document_id=document.id,
            version=1 if current is None else current.version + 1,
            content_sha256=sha256,
            encoding=encoding,
            mime_type="text/plain",
            storage_uri=storage_uri,
            byte_size=byte_size,
            normalization_map_id=None,
            supersedes_version_id=current.id if current else None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(document_version)
        await self.session.flush()
        document.current_version_id = document_version.id
        # Compatibility mirrors remain populated until the legacy columns are
        # removed in a deployment where downgrade is no longer required.
        document.version = sha256
        document.sha256 = sha256
        document.encoding = encoding
        document.storage_uri = storage_uri
        document.byte_size = byte_size
        document.normalization_map_version = None
        document.normalization_map = None
        document.updated_at = now
        await self.session.flush()
        return document_version

    async def invalidate_source_version_dependencies(
        self,
        *,
        novel_id: UUID,
        source_document_version_id: UUID,
        invalidated_at: datetime,
    ) -> None:
        character_ids = select(CharacterORM.id).where(CharacterORM.novel_id == novel_id)
        await self.session.execute(
            update(FeatureObservationORM)
            .where(
                FeatureObservationORM.source_document_version_id == source_document_version_id,
                FeatureObservationORM.record_status == "active",
            )
            .values(
                record_status="invalidated",
                valid_to=invalidated_at,
                invalidated_at=invalidated_at,
                invalidated_by_run_id=None,
                updated_at=invalidated_at,
            )
        )
        await self.session.execute(
            update(CharacterAppearanceStateORM)
            .where(
                CharacterAppearanceStateORM.character_id.in_(character_ids),
                CharacterAppearanceStateORM.aggregation_fingerprint.is_not(None),
                CharacterAppearanceStateORM.record_status == "active",
            )
            .values(record_status="invalidated", updated_at=invalidated_at)
        )
        await self.session.execute(
            update(CharacterRenderProfileORM)
            .where(
                CharacterRenderProfileORM.character_id.in_(character_ids),
                CharacterRenderProfileORM.record_status == "active",
            )
            .values(record_status="stale", updated_at=invalidated_at)
        )
        await self.session.execute(
            update(CharacterConflictORM)
            .where(
                CharacterConflictORM.character_id.in_(character_ids),
                CharacterConflictORM.status == "pending",
            )
            .values(
                status="superseded",
                revision=CharacterConflictORM.revision + 1,
                updated_at=invalidated_at,
            )
        )

    async def get_novel(self, novel_id: UUID) -> NovelORM | None:
        return await self.session.get(NovelORM, novel_id)

    async def get_document(self, document_id: UUID) -> SourceDocumentORM | None:
        return await self.session.get(SourceDocumentORM, document_id)

    async def latest_document(self, novel_id: UUID) -> SourceDocumentORM | None:
        return cast(
            SourceDocumentORM | None,
            await self.session.scalar(
                select(SourceDocumentORM)
                .where(SourceDocumentORM.novel_id == novel_id)
                .order_by(SourceDocumentORM.created_at.desc())
            ),
        )

    async def latest_document_version(self, novel_id: UUID) -> SourceDocumentVersionORM | None:
        return cast(
            SourceDocumentVersionORM | None,
            await self.session.scalar(
                select(SourceDocumentVersionORM)
                .join(
                    SourceDocumentORM,
                    SourceDocumentVersionORM.id == SourceDocumentORM.current_version_id,
                )
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
        return await self._create_run(
            novel_id=novel_id,
            idempotency_key=idempotency_key,
            run_type="text_ingestion",
            step_key="normalize_and_chunk",
        )

    async def create_extraction_run(
        self, novel_id: UUID, idempotency_key: str
    ) -> tuple[PipelineRunORM, PipelineStepORM]:
        return await self._create_run(
            novel_id=novel_id,
            idempotency_key=idempotency_key,
            run_type="character_extraction",
            step_key="extract_characters",
        )

    async def create_analysis_run(
        self, novel_id: UUID, idempotency_key: str
    ) -> tuple[PipelineRunORM, PipelineStepORM]:
        return await self._create_run(
            novel_id=novel_id,
            idempotency_key=idempotency_key,
            run_type="text_analysis",
            step_key="normalize_and_chunk",
        )

    async def _create_run(
        self, *, novel_id: UUID, idempotency_key: str, run_type: str, step_key: str
    ) -> tuple[PipelineRunORM, PipelineStepORM]:
        now = datetime.now(UTC)
        run = PipelineRunORM(
            id=uuid4(),
            novel_id=novel_id,
            run_type=run_type,
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
            step_key=step_key,
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
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="run.created",
            payload={"run_type": run_type, "step_key": step_key, "status": "queued"},
        )
        return run, step

    async def persist_processed_text(
        self,
        *,
        novel: NovelORM,
        document: SourceDocumentORM,
        document_version: SourceDocumentVersionORM,
        normalized: NormalizedText,
        chapters: list[ChapterBoundary],
        chunks: list[TextChunk],
    ) -> None:
        existing_chunks = list(
            await self.session.scalars(
                select(TextChunkORM)
                .where(TextChunkORM.source_document_version_id == document_version.id)
                .order_by(TextChunkORM.ordinal)
            )
        )
        if existing_chunks:
            existing_signature = [
                (
                    item.ordinal,
                    item.content_hash,
                    item.normalized_char_start,
                    item.normalized_char_end,
                )
                for item in existing_chunks
            ]
            incoming_signature = [
                (item.ordinal, item.content_hash, item.normalized_start, item.normalized_end)
                for item in chunks
            ]
            if existing_signature != incoming_signature:
                raise RuntimeError("immutable_document_version_conflict")
            await self._persist_normalization_map(document, document_version, normalized)
            novel.status = "chunked"
            novel.updated_at = datetime.now(UTC)
            await self.session.flush()
            return

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
                    source_document_version_id=document_version.id,
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
                    source_document_version_id=document_version.id,
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
        await self._persist_normalization_map(document, document_version, normalized)
        novel.status = "chunked"
        novel.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def _persist_normalization_map(
        self,
        document: SourceDocumentORM,
        document_version: SourceDocumentVersionORM,
        normalized: NormalizedText,
    ) -> None:
        now = datetime.now(UTC)
        normalization_map = await self.session.scalar(
            select(NormalizationMapORM).where(
                NormalizationMapORM.source_document_version_id == document_version.id
            )
        )
        if normalization_map is None:
            normalization_map = NormalizationMapORM(
                id=uuid4(),
                source_document_version_id=document_version.id,
                algorithm_version=normalized.map_version,
                original_boundaries=normalized.original_boundaries,
                created_at=now,
                updated_at=now,
            )
            self.session.add(normalization_map)
            await self.session.flush()
            document_version.normalization_map_id = normalization_map.id
        elif (
            normalization_map.algorithm_version != normalized.map_version
            or normalization_map.original_boundaries != normalized.original_boundaries
        ):
            raise RuntimeError("immutable_normalization_map_conflict")
        document.normalization_map_version = normalized.map_version
        document.normalization_map = {"original_boundaries": normalized.original_boundaries}
        document.updated_at = now
        document_version.updated_at = now

    async def get_counts(self, novel_id: UUID) -> tuple[int, int]:
        version = await self.latest_document_version(novel_id)
        if version is None:
            return 0, 0
        chapters = await self.session.scalar(
            select(func.count())
            .select_from(ChapterORM)
            .where(ChapterORM.source_document_version_id == version.id)
        )
        chunks = await self.session.scalar(
            select(func.count())
            .select_from(TextChunkORM)
            .where(TextChunkORM.source_document_version_id == version.id)
        )
        return chapters or 0, chunks or 0
