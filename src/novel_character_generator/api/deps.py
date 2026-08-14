from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    from novel_character_generator.api.app import session_factory

    async with session_factory() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    from novel_character_generator.api.app import session_factory

    return session_factory
