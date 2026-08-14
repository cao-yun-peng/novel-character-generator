from sqlite3 import Connection as SQLiteConnection
from typing import Any, cast

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from novel_character_generator.settings import get_settings

engine: AsyncEngine = create_async_engine(get_settings().database_url)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def configure_sqlite(connection: object, _: object) -> None:
    module_name = connection.__class__.__module__
    if not isinstance(connection, SQLiteConnection) and "sqlite" not in module_name:
        return
    cursor = cast(Any, connection).cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


async def dispose_engine() -> None:
    await engine.dispose()
