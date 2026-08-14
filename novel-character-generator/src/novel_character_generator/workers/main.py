import argparse
import asyncio
from uuid import UUID

from novel_character_generator.infrastructure.db.session import session_factory
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


async def run_once(run_id: UUID) -> None:
    settings = get_settings()
    async with session_factory() as session:
        await process_ingestion_run(
            session,
            LocalArtifactStore(settings.artifact_local_root),
            run_id,
            target_tokens=settings.max_chunk_input_tokens,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", type=UUID)
    arguments = parser.parse_args()
    asyncio.run(run_once(arguments.run_id))


if __name__ == "__main__":
    main()
