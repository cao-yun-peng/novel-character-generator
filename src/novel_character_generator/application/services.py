from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.domain.models import RunKind
from novel_character_generator.infrastructure.db.orm import NovelORM, PipelineRunORM
from novel_character_generator.infrastructure.db.repositories import create_novel, create_run


class NovelService:
    async def import_novel(self, session: AsyncSession, title: str, text: str) -> NovelORM:
        digest = hashlib.sha256(text.encode()).hexdigest()
        return await create_novel(session, title, text, digest)

    async def submit_extraction(
        self, session: AsyncSession, novel_id: UUID, idempotency_key: str
    ) -> PipelineRunORM:
        novel = await session.get(NovelORM, novel_id)
        if novel is None:
            raise LookupError("novel_not_found")
        return await create_run(session, novel_id, RunKind.EXTRACT, idempotency_key, {})

    async def submit_image(
        self,
        session: AsyncSession,
        novel_id: UUID,
        character_id: UUID,
        idempotency_key: str,
    ) -> PipelineRunORM:
        return await create_run(
            session,
            novel_id,
            RunKind.IMAGE,
            idempotency_key,
            {"character_id": str(character_id)},
        )

    async def get_run(self, session: AsyncSession, run_id: UUID) -> PipelineRunORM | None:
        return await session.get(PipelineRunORM, run_id)

    async def cancel(self, session: AsyncSession, run_id: UUID) -> PipelineRunORM | None:
        run = await session.get(PipelineRunORM, run_id)
        if run is not None:
            run.cancel_requested = True
            await session.commit()
        return run

    async def list_characters(self, session: AsyncSession, novel_id: UUID) -> list[object]:
        from novel_character_generator.infrastructure.db.orm import CharacterORM

        return list(
            (await session.scalars(select(CharacterORM).where(CharacterORM.novel_id == novel_id))).all()
        )
