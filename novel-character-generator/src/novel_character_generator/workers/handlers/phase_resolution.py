from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.services.phase_resolution_service import (
    resolve_character_phases,
)
from novel_character_generator.infrastructure.db.orm import (
    FeatureObservationORM,
    PipelineRunORM,
    PipelineStepORM,
)
from novel_character_generator.infrastructure.db.repositories.extraction import (
    ExtractionRepository,
)
from novel_character_generator.infrastructure.db.repositories.phase_resolution import (
    PhaseResolutionRepository,
)
from novel_character_generator.workers.task_claim import (
    checkpoint_step,
    complete_step_and_enqueue,
    mark_cancelled,
    record_step_error,
    start_step,
)


async def process_phase_resolution_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    max_attempts: int = 3,
    lease_seconds: int = 120,
) -> None:
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type not in {"character_extraction", "text_analysis"}:
        raise ValueError("phase_resolution_run_not_found")
    step = await session.scalar(
        select(PipelineStepORM).where(
            PipelineStepORM.run_id == run_id,
            PipelineStepORM.step_key == "resolve_character_phases",
        )
    )
    if step is None:
        raise RuntimeError("phase_resolution_step_not_found")
    if step.status == "succeeded":
        return
    if step.status not in {"queued", "retry_scheduled", "claimed"}:
        raise ValueError("phase_resolution_step_not_runnable")
    if run.cancel_requested:
        await mark_cancelled(
            session,
            step=step,
            run=run,
            expected_generation=step.lease_generation,
        )
        return

    step_id = step.id
    expected_generation = await start_step(session, step=step, run=run)
    try:
        repository = PhaseResolutionRepository(session)
        extraction_repository = ExtractionRepository(session)
        document = await extraction_repository.source_document(run.novel_id)
        timeline = await repository.canonical_timeline(run.novel_id)
        character_ids = await repository.affected_character_ids(run.id)
        cursor = step.cursor or {}
        start_index = int(cursor.get("current_character_index", 0))
        review_count = int(cursor.get("needs_review_count", 0))

        for index, character_id in enumerate(character_ids):
            if index < start_index:
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
            request = await repository.build_input(
                run=run,
                character_id=character_id,
                timeline_id=timeline.id,
            )
            result = resolve_character_phases(request)
            review_count += sum(
                decision.status == "needs_review" for decision in result.scope_decisions
            )
            await repository.materialize(
                run=run,
                source_document_version_id=document.id,
                request=request,
                result=result,
            )
            await checkpoint_step(
                session,
                step=step,
                expected_generation=expected_generation,
                cursor={
                    "schema_version": "character-phase-resolution-v1",
                    "current_character_index": index + 1,
                    "character_count": len(character_ids),
                    "needs_review_count": review_count,
                    "completed_step_keys": [],
                },
                lease_seconds=lease_seconds,
            )

        await repository.mark_unbound_signals_unresolved(run.id)
        extractor_versions = list(
            await session.scalars(
                select(FeatureObservationORM.extractor_version)
                .where(FeatureObservationORM.extraction_run_id == run.id)
                .distinct()
            )
        )
        if len(extractor_versions) == 1:
            await extraction_repository.supersede_prior_extractor_observations(
                run=run,
                document=document,
                extractor_version=extractor_versions[0],
            )
        elif extractor_versions:
            await extraction_repository.supersede_all_prior_automatic_observations(
                run=run,
                document=document,
            )
        await repository.activate_final_observations(run.id)
        await complete_step_and_enqueue(
            session,
            step=step,
            run=run,
            expected_generation=expected_generation,
            cursor={
                "schema_version": "character-phase-resolution-v1",
                "current_character_index": len(character_ids),
                "character_count": len(character_ids),
                "needs_review_count": review_count,
                "completed_step_keys": [step.step_key],
            },
            next_step_key="aggregate_appearance",
        )
    except Exception as error:
        await record_step_error(
            session,
            step_id=step_id,
            run_id=run_id,
            error_code="phase_resolution_failed",
            error=error,
            max_attempts=max_attempts,
            expected_generation=expected_generation,
        )
        await session.commit()
        raise
