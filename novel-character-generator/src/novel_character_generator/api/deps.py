from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.infrastructure.db.session import session_factory
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


def get_artifact_store() -> LocalArtifactStore:
    return LocalArtifactStore(get_settings().artifact_local_root)
