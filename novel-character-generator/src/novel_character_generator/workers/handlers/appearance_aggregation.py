import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.services.appearance_aggregation_service import (
    AppearanceAggregationService,
)
from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.workers.task_claim import (
    checkpoint_step,
    complete_step,
    mark_cancelled,
    record_step_error,
    start_step,
)

logger = logging.getLogger(__name__)


async def process_appearance_aggregation_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    max_attempts: int = 3,
    lease_seconds: int = 120,
) -> None:
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type not in {"character_extraction", "text_analysis"}:
        raise ValueError("appearance_aggregation_run_not_found")
    step = await session.scalar(
        select(PipelineStepORM).where(
            PipelineStepORM.run_id == run_id,
            PipelineStepORM.step_key == "aggregate_appearance",
        )
    )
    if step is None:
        raise RuntimeError("appearance_aggregation_step_not_found")
    if step.status == "succeeded":
        return
    if step.status not in {"queued", "retry_scheduled", "claimed"}:
        raise ValueError("appearance_aggregation_step_not_runnable")
    if run.cancel_requested:
        await mark_cancelled(
            session,
            step=step,
            run=run,
            expected_generation=step.lease_generation,
        )
        return
    step_id = step.id
    persisted_run_id = run.id
    expected_generation = await start_step(session, step=step, run=run)
    try:
        service = AppearanceAggregationService(session)
        document = await service.source_document_version(run.novel_id)
        character_ids = await service.affected_character_ids(
            novel_id=run.novel_id,
            source_document_version_id=document.id,
        )
        cursor = step.cursor or {}
        completed = {str(item) for item in cursor.get("completed_character_ids", [])}
        await session.commit()

        for character_id in character_ids:
            if str(character_id) in completed:
                continue
            await session.refresh(run, attribute_names=["cancel_requested"])
            if run.cancel_requested:
                await mark_cancelled(
                    session,
                    step=step,
                    run=run,
                    expected_generation=expected_generation,
                )
                return
            await service.aggregate_character(
                run=run,
                step_id=step.id,
                expected_generation=expected_generation,
                character_id=character_id,
                source_document_version_id=document.id,
            )
            completed.add(str(character_id))
            await checkpoint_step(
                session,
                step=step,
                expected_generation=expected_generation,
                cursor={
                    "schema_version": "v1",
                    "source_document_version_id": str(document.id),
                    "completed_character_ids": sorted(completed),
                },
                lease_seconds=lease_seconds,
            )
        await complete_step(
            session,
            step=step,
            run=run,
            expected_generation=expected_generation,
            cursor={
                "schema_version": "v1",
                "source_document_version_id": str(document.id),
                "completed_character_ids": sorted(completed),
                "completed_step_keys": [step.step_key],
            },
        )
    except Exception as error:
        logger.exception(
            "appearance.aggregation.failed",
            extra={
                "event_name": "appearance.aggregation.failed",
                "run_id": str(run_id),
                "step_id": str(step_id),
                "lease_generation": expected_generation,
                "error_code": "appearance_aggregation_failed",
            },
        )
        await record_step_error(
            session,
            step_id=step_id,
            run_id=persisted_run_id,
            error_code="appearance_aggregation_failed",
            error=error,
            max_attempts=max_attempts,
            expected_generation=expected_generation,
        )
        raise
