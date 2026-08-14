import argparse
import asyncio
from uuid import UUID

from novel_character_generator.infrastructure.db.orm import PipelineRunORM
from novel_character_generator.infrastructure.db.session import session_factory
from novel_character_generator.infrastructure.llm.mock import MockExtractionProvider
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.settings import get_settings
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run


async def run_once(run_id: UUID) -> None:
    settings = get_settings()
    async with session_factory() as session:
        run = await session.get(PipelineRunORM, run_id)
        if run is None:
            raise ValueError("run_not_found")
        if run.run_type == "text_ingestion":
            await process_ingestion_run(
                session,
                LocalArtifactStore(settings.artifact_local_root),
                run_id,
                target_tokens=settings.max_chunk_input_tokens,
            )
        elif run.run_type == "character_extraction":
            await process_extraction_run(session, MockExtractionProvider(), run_id)
        else:
            raise ValueError("unsupported_run_type")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", type=UUID)
    arguments = parser.parse_args()
    asyncio.run(run_once(arguments.run_id))


if __name__ == "__main__":
    main()
