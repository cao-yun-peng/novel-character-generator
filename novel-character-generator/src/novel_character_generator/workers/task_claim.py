from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from novel_character_generator.infrastructure.db.orm import PipelineRunORM, PipelineStepORM
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event


class LeaseLostError(RuntimeError):
    pass


def _runnable(now: datetime) -> ColumnElement[bool]:
    return or_(
        and_(
            PipelineStepORM.status.in_(("queued", "retry_scheduled")),
            or_(PipelineStepORM.next_attempt_at.is_(None), PipelineStepORM.next_attempt_at <= now),
        ),
        and_(
            PipelineStepORM.status.in_(("claimed", "running")),
            PipelineStepORM.lease_expires_at.is_not(None),
            PipelineStepORM.lease_expires_at <= now,
        ),
    )


async def claim_next_step(
    session: AsyncSession, *, worker_id: str, lease_seconds: int
) -> PipelineStepORM | None:
    """Atomically claim one due step, including work whose lease expired."""
    now = datetime.now(UTC)
    runnable = _runnable(now)
    candidate_id = await session.scalar(
        select(PipelineStepORM.id)
        .where(runnable)
        .order_by(PipelineStepORM.created_at, PipelineStepORM.id)
        .limit(1)
    )
    if candidate_id is None:
        await session.rollback()
        return None

    claimed_id = await session.scalar(
        update(PipelineStepORM)
        .where(PipelineStepORM.id == candidate_id, runnable)
        .values(
            status="claimed",
            lease_owner=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            lease_generation=PipelineStepORM.lease_generation + 1,
            heartbeat_at=now,
            updated_at=now,
        )
        .returning(PipelineStepORM.id)
    )
    if claimed_id is None:
        await session.rollback()
        return None
    claimed_step = await session.get(PipelineStepORM, claimed_id)
    if claimed_step is None:
        await session.rollback()
        return None
    await append_run_event(
        session,
        run_id=claimed_step.run_id,
        event_type="step.claimed",
        payload={
            "step_id": str(claimed_step.id),
            "worker_id": worker_id,
            "lease_generation": claimed_step.lease_generation,
        },
    )
    await session.commit()
    return claimed_step


async def record_step_error(
    session: AsyncSession,
    *,
    step_id: UUID,
    run_id: UUID,
    error_code: str,
    error: Exception,
    max_attempts: int,
    expected_generation: int,
) -> None:
    await session.rollback()
    step = await session.get(PipelineStepORM, step_id)
    run = await session.get(PipelineRunORM, run_id)
    if step is None or run is None:
        return
    if step.lease_generation != expected_generation:
        # A newer worker owns the step. The stale worker must not change its
        # state or the enclosing run.
        await session.rollback()
        return

    now = datetime.now(UTC)
    retryable = step.attempt < max_attempts and not run.cancel_requested
    next_status = "retry_scheduled" if retryable else "failed"
    next_attempt_at = (
        now + timedelta(seconds=min(60, 2 ** max(0, step.attempt - 1))) if retryable else None
    )
    updated_id = await session.scalar(
        update(PipelineStepORM)
        .where(
            PipelineStepORM.id == step_id,
            PipelineStepORM.lease_generation == expected_generation,
        )
        .values(
            status=next_status,
            next_attempt_at=next_attempt_at,
            error_code=error_code,
            error_message=str(error)[:2_000],
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=now,
            updated_at=now,
        )
        .returning(PipelineStepORM.id)
    )
    if updated_id is None:
        await session.rollback()
        return
    await append_run_event(
        session,
        run_id=run_id,
        event_type="step.retry_scheduled" if retryable else "step.failed",
        payload={
            "step_id": str(step_id),
            "attempt": step.attempt,
            "error_code": error_code,
            "lease_generation": expected_generation,
        },
    )
    run.status = "queued" if retryable else "failed"
    run.completed_at = None if retryable else now
    run.updated_at = now
    await session.commit()


async def mark_cancelled(
    session: AsyncSession,
    *,
    step: PipelineStepORM,
    run: PipelineRunORM,
    expected_generation: int,
) -> None:
    now = datetime.now(UTC)
    updated_id = await session.scalar(
        update(PipelineStepORM)
        .where(
            PipelineStepORM.id == step.id,
            PipelineStepORM.lease_generation == expected_generation,
        )
        .values(
            status="cancelled",
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=now,
            updated_at=now,
        )
        .returning(PipelineStepORM.id)
    )
    if updated_id is None:
        await session.rollback()
        raise LeaseLostError("step_lease_lost")
    await append_run_event(
        session,
        run_id=run.id,
        event_type="step.cancelled",
        payload={"step_id": str(step.id), "lease_generation": expected_generation},
    )
    run.status = "cancelled"
    run.completed_at = now
    run.updated_at = now
    await session.commit()


async def start_step(
    session: AsyncSession, *, step: PipelineStepORM, run: PipelineRunORM
) -> int:
    """Move a claimed/direct step to running with generation fencing."""
    now = datetime.now(UTC)
    expected_generation = step.lease_generation
    updated_id = await session.scalar(
        update(PipelineStepORM)
        .where(
            PipelineStepORM.id == step.id,
            PipelineStepORM.lease_generation == expected_generation,
            PipelineStepORM.status == step.status,
        )
        .values(
            status="running",
            attempt=PipelineStepORM.attempt + 1,
            heartbeat_at=now,
            updated_at=now,
        )
        .returning(PipelineStepORM.id)
    )
    if updated_id is None:
        await session.rollback()
        raise LeaseLostError("step_lease_lost")
    await append_run_event(
        session,
        run_id=run.id,
        event_type="step.running",
        payload={
            "step_id": str(step.id),
            "attempt": step.attempt,
            "lease_generation": expected_generation,
        },
    )
    run.status = "running"
    run.updated_at = now
    await session.commit()
    await session.refresh(step)
    return expected_generation


async def checkpoint_step(
    session: AsyncSession,
    *,
    step: PipelineStepORM,
    expected_generation: int,
    cursor: dict[str, object],
    lease_seconds: int,
) -> None:
    """Persist progress only if this worker still owns the lease generation."""
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "cursor": cursor,
        "heartbeat_at": now,
        "updated_at": now,
    }
    if step.lease_owner is not None:
        values["lease_expires_at"] = now + timedelta(seconds=lease_seconds)
    updated_id = await session.scalar(
        update(PipelineStepORM)
        .where(
            PipelineStepORM.id == step.id,
            PipelineStepORM.lease_generation == expected_generation,
        )
        .values(**values)
        .returning(PipelineStepORM.id)
    )
    if updated_id is None:
        await session.rollback()
        raise LeaseLostError("step_lease_lost")
    await append_run_event(
        session,
        run_id=step.run_id,
        event_type="step.progress",
        payload={
            "step_id": str(step.id),
            "cursor": cursor,
            "lease_generation": expected_generation,
        },
    )
    await session.commit()
    await session.refresh(step)


async def complete_step(
    session: AsyncSession,
    *,
    step: PipelineStepORM,
    run: PipelineRunORM,
    expected_generation: int,
    cursor: dict[str, object],
) -> None:
    now = datetime.now(UTC)
    updated_id = await session.scalar(
        update(PipelineStepORM)
        .where(
            PipelineStepORM.id == step.id,
            PipelineStepORM.lease_generation == expected_generation,
        )
        .values(
            status="succeeded",
            cursor=cursor,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=now,
            updated_at=now,
        )
        .returning(PipelineStepORM.id)
    )
    if updated_id is None:
        await session.rollback()
        raise LeaseLostError("step_lease_lost")
    await append_run_event(
        session,
        run_id=run.id,
        event_type="step.succeeded",
        payload={
            "step_id": str(step.id),
            "cursor": cursor,
            "lease_generation": expected_generation,
        },
    )
    run.status = "succeeded"
    run.completed_at = now
    run.updated_at = now
    await session.commit()


async def complete_step_and_enqueue(
    session: AsyncSession,
    *,
    step: PipelineStepORM,
    run: PipelineRunORM,
    expected_generation: int,
    cursor: dict[str, object],
    next_step_key: str,
) -> PipelineStepORM:
    """Complete one workflow step and atomically make its successor runnable."""
    now = datetime.now(UTC)
    updated_id = await session.scalar(
        update(PipelineStepORM)
        .where(
            PipelineStepORM.id == step.id,
            PipelineStepORM.status == "running",
            PipelineStepORM.lease_generation == expected_generation,
        )
        .values(
            status="succeeded",
            cursor=cursor,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=now,
            updated_at=now,
        )
        .returning(PipelineStepORM.id)
    )
    if updated_id is None:
        await session.rollback()
        raise LeaseLostError("step_lease_lost")
    next_step = await session.scalar(
        select(PipelineStepORM).where(
            PipelineStepORM.run_id == run.id,
            PipelineStepORM.step_key == next_step_key,
        )
    )
    if next_step is None:
        next_step = PipelineStepORM(
            id=uuid4(),
            run_id=run.id,
            step_key=next_step_key,
            status="queued",
            attempt=0,
            lease_owner=None,
            lease_expires_at=None,
            lease_generation=0,
            heartbeat_at=None,
            next_attempt_at=None,
            cursor={"schema_version": "v1", "current_chunk_ordinal": 0},
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        session.add(next_step)
        await session.flush()
    await append_run_event(
        session,
        run_id=run.id,
        event_type="step.succeeded",
        payload={
            "step_id": str(step.id),
            "cursor": cursor,
            "lease_generation": expected_generation,
        },
    )
    await append_run_event(
        session,
        run_id=run.id,
        event_type="step.queued",
        payload={"step_id": str(next_step.id), "step_key": next_step.step_key},
    )
    run.status = "queued"
    run.completed_at = None
    run.updated_at = now
    await session.commit()
    return next_step
