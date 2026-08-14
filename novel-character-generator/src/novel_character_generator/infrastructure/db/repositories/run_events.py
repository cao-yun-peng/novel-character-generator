from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.infrastructure.db.orm import RunEventORM


async def append_run_event(
    session: AsyncSession,
    *,
    run_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> RunEventORM:
    last_sequence = await session.scalar(
        select(func.max(RunEventORM.sequence)).where(RunEventORM.run_id == run_id)
    )
    event = RunEventORM(
        id=uuid4(),
        run_id=run_id,
        sequence=(last_sequence or 0) + 1,
        event_type=event_type,
        payload=payload,
        created_at=datetime.now(UTC),
    )
    session.add(event)
    await session.flush()
    return event


async def read_run_events(
    session: AsyncSession, *, run_id: UUID, after_sequence: int, limit: int = 100
) -> list[RunEventORM]:
    events = await session.scalars(
        select(RunEventORM)
        .where(RunEventORM.run_id == run_id, RunEventORM.sequence > after_sequence)
        .order_by(RunEventORM.sequence)
        .limit(limit)
    )
    return list(events)
