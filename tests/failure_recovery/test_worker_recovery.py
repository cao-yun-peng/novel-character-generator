from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from novel_character_generator.application.services import NovelService
from novel_character_generator.infrastructure.db.orm import Base, PipelineStepORM
from novel_character_generator.infrastructure.db.repositories import claim_step
from novel_character_generator.infrastructure.db.session import create_engine, create_session_factory
from novel_character_generator.settings import Settings


async def test_expired_lease_is_reclaimed_without_new_step(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'lease.db'}")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    service = NovelService()
    async with factory() as session:
        novel = await service.import_novel(session, "示例", "角色：林昭|黑发")
        await service.submit_extraction(session, novel.id, "recover-once")
        first = await claim_step(session, "worker-a", 120)
        assert first is not None
        first.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with factory() as session:
        recovered = await claim_step(session, "worker-b", 120)
        count = len((await session.scalars(PipelineStepORM.__table__.select())).all())
        assert recovered is not None
        assert recovered.id == first.id
        assert recovered.lease_owner == "worker-b"
        assert recovered.lease_generation == 2
        assert count == 1

    await engine.dispose()
