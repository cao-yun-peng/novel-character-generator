from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from novel_character_generator.settings import get_settings

engine: AsyncEngine = create_async_engine(get_settings().database_url)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def dispose_engine() -> None:
    await engine.dispose()
