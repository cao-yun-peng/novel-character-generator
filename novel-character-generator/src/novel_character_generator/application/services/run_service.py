from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event


@dataclass(frozen=True)
class StepDetails:
    id: UUID
    step_key: str
    status: str
    attempt: int
    cursor: dict[str, object] | None
    error_code: str | None


@dataclass(frozen=True)
class RunDetails:
    id: UUID
    novel_id: UUID
    run_type: str
    status: str
    cancel_requested: bool
    steps: list[StepDetails]


class RunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def details(self, run_id: UUID) -> RunDetails | None:
        run = await self.session.get(PipelineRunORM, run_id)
        if run is None:
            return None
        steps = list(
            await self.session.scalars(
                select(PipelineStepORM)
                .where(PipelineStepORM.run_id == run_id)
                .order_by(PipelineStepORM.created_at)
            )
        )
        return RunDetails(
            id=run.id,
            novel_id=run.novel_id,
            run_type=run.run_type,
            status=run.status,
            cancel_requested=run.cancel_requested,
            steps=[
                StepDetails(
                    id=step.id,
                    step_key=step.step_key,
                    status=step.status,
                    attempt=step.attempt,
                    cursor=step.cursor,
                    error_code=step.error_code,
                )
                for step in steps
            ],
        )

    async def request_cancel(self, run_id: UUID) -> RunDetails | None:
        run = await self.session.get(PipelineRunORM, run_id)
        if run is None:
            return None
        if run.status in {"succeeded", "cancelled", "failed"}:
            raise ValueError("run_not_cancellable")

        now = datetime.now(UTC)
        run.cancel_requested = True
        run.updated_at = now
        steps = list(
            await self.session.scalars(
                select(PipelineStepORM).where(PipelineStepORM.run_id == run_id)
            )
        )
        if all(step.status in {"queued", "retry_scheduled", "cancelled"} for step in steps):
            for step in steps:
                if step.status != "cancelled":
                    step.status = "cancelled"
                    step.next_attempt_at = None
                    step.updated_at = now
            run.status = "cancelled"
            run.completed_at = now
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="run.cancel_requested",
            payload={"status": run.status},
        )
        await self.session.commit()
        return await self.details(run_id)

    async def retry(self, run_id: UUID, *, max_attempts: int) -> RunDetails | None:
        run = await self.session.get(PipelineRunORM, run_id)
        if run is None:
            return None
        if run.status != "failed":
            raise ValueError("run_not_retryable")
        steps = list(
            await self.session.scalars(
                select(PipelineStepORM).where(PipelineStepORM.run_id == run_id)
            )
        )
        failed_steps = [step for step in steps if step.status == "failed"]
        if not failed_steps:
            raise ValueError("run_has_no_failed_step")
        if any(step.attempt >= max_attempts for step in failed_steps):
            raise ValueError("task_attempts_exhausted")

        now = datetime.now(UTC)
        for step in failed_steps:
            step.status = "retry_scheduled"
            step.next_attempt_at = now
            step.error_code = None
            step.error_message = None
            step.lease_owner = None
            step.lease_expires_at = None
            step.updated_at = now
        run.status = "queued"
        run.cancel_requested = False
        run.completed_at = None
        run.updated_at = now
        await append_run_event(
            self.session,
            run_id=run.id,
            event_type="run.retry_requested",
            payload={"step_ids": [str(step.id) for step in failed_steps]},
        )
        await self.session.commit()
        return await self.details(run_id)
