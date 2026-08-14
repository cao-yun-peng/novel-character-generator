from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.infrastructure.db.session import session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
