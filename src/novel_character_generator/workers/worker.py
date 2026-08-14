from __future__ import annotations

import asyncio
import socket
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from novel_character_generator.application.ports import ImageProvider
from novel_character_generator.domain.models import Character
from novel_character_generator.infrastructure.db.orm import CharacterORM, NovelORM, PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.db.repositories import (
    claim_step,
    complete_step,
    fail_step,
    save_character,
    save_image,
)
from novel_character_generator.infrastructure.providers.mock import MockExtractionProvider
from novel_character_generator.infrastructure.storage import LocalArtifactStore
from novel_character_generator.settings import Settings


class Worker:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        image_provider: ImageProvider,
        artifact_store: LocalArtifactStore,
        owner: str | None = None,
    ) -> None:
        self.factory = factory
        self.settings = settings
        self.extraction_provider = MockExtractionProvider()
        self.image_provider = image_provider
        self.artifact_store = artifact_store
        self.owner = owner or socket.gethostname()

    async def run_once(self) -> bool:
        async with self.factory() as session:
            step = await claim_step(session, self.owner, self.settings.worker_lease_seconds)
        if step is None:
            return False
        try:
            async with self.factory() as session:
                current = await session.get(PipelineStepORM, step.id)
                if current is None:
                    return False
                run = await session.get(PipelineRunORM, current.run_id)
                if run is None:
                    raise LookupError("run_not_found")
                if run.cancel_requested:
                    raise RuntimeError("run_cancelled")
                if run.kind == "extract":
                    result = await self._extract(session, run)
                elif run.kind == "image":
                    result = await self._image(session, current, run)
                else:
                    raise ValueError("unsupported_run_kind")
                await complete_step(session, current, result)
        except Exception as exc:
            async with self.factory() as session:
                current = await session.get(PipelineStepORM, step.id)
                if current is not None:
                    await fail_step(session, current, type(exc).__name__, self.settings.max_task_attempts)
        return True

    async def _extract(self, session: AsyncSession, run: PipelineRunORM) -> dict[str, object]:
        novel = await session.get(NovelORM, run.novel_id)
        if novel is None:
            raise LookupError("novel_not_found")
        extracted = await self.extraction_provider.extract(novel.source_text)
        character_ids: list[str] = []
        for item in extracted:
            marker = f"角色：{item.name}"
            start = novel.source_text.find(marker)
            saved = await save_character(
                session,
                novel.id,
                item.name,
                item.description,
                novel.source_text[start:novel.source_text.find("\n", start) if "\n" in novel.source_text[start:] else None],
                start,
            )
            character_ids.append(str(saved.id))
        return {"character_ids": character_ids}

    async def _image(
        self, session: AsyncSession, step: PipelineStepORM, run: PipelineRunORM
    ) -> dict[str, object]:
        character_id = UUID(run.input_payload["character_id"])
        row = await session.scalar(select(CharacterORM).where(CharacterORM.id == character_id))
        if row is None:
            raise LookupError("character_not_found")
        character = Character(
            id=row.id, novel_id=row.novel_id, name=row.name, description=row.description
        )
        request_id = step.external_request_id
        if request_id is None:
            request_id = await self.image_provider.submit(character, f"{run.id}:{step.step_key}")
            step.external_request_id = request_id
            await session.commit()
        result = await self.image_provider.fetch_result(request_id)
        uri = await self.artifact_store.put(f"images/{request_id}.mock", result.content)
        image = await save_image(
            session,
            character.id,
            uri,
            f"portrait of {character.name}, {character.description or ''}",
            request_id,
        )
        return {"image_id": str(image.id), "artifact_uri": uri}

    async def serve(self) -> None:
        while True:
            worked = await self.run_once()
            if not worked:
                await asyncio.sleep(self.settings.worker_poll_seconds)
