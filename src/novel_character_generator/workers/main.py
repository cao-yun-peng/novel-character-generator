from __future__ import annotations

import asyncio

from novel_character_generator.infrastructure.db.session import create_engine, create_session_factory
from novel_character_generator.infrastructure.providers.mock import MockImageProvider
from novel_character_generator.infrastructure.storage import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.worker import Worker


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    worker = Worker(
        create_session_factory(engine),
        settings,
        MockImageProvider(),
        LocalArtifactStore(settings.artifact_root),
    )
    try:
        await worker.serve()
    finally:
        await engine.dispose()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
