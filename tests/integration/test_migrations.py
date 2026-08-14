from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine


async def test_alembic_upgrade_creates_vertical_slice_tables(tmp_path: Path) -> None:
    database = tmp_path / "migration.db"
    subprocess.run(
        [
            "alembic",
            "-c",
            "alembic.ini",
            "-x",
            f"database_url=sqlite+aiosqlite:///{database}",
            "upgrade",
            "head",
        ],
        check=True,
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    await engine.dispose()
    assert {
        "novels",
        "characters",
        "pipeline_runs",
        "pipeline_steps",
        "feature_observations",
        "generated_images",
    } <= set(tables)
