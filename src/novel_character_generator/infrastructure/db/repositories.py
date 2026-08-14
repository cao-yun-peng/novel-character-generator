from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.domain.models import RunKind, RunStatus, StepStatus
from novel_character_generator.infrastructure.db.orm import (
    CharacterORM,
    FeatureObservationORM,
    GeneratedImageORM,
    NovelORM,
    PipelineRunORM,
    PipelineStepORM,
)


def now() -> datetime:
    return datetime.now(UTC)


async def create_novel(session: AsyncSession, title: str, text: str, digest: str) -> NovelORM:
    existing = await session.scalar(select(NovelORM).where(NovelORM.content_sha256 == digest))
    if existing is not None:
        return existing
    novel = NovelORM(
        id=uuid4(), title=title, source_text=text, content_sha256=digest, created_at=now(), updated_at=now()
    )
    session.add(novel)
    await session.commit()
    return novel


async def create_run(
    session: AsyncSession,
    novel_id: UUID,
    kind: RunKind,
    idempotency_key: str,
    payload: dict[str, Any],
) -> PipelineRunORM:
    existing = await session.scalar(
        select(PipelineRunORM).where(PipelineRunORM.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    run = PipelineRunORM(
        id=uuid4(), novel_id=novel_id, kind=kind.value, status=RunStatus.QUEUED.value,
        idempotency_key=idempotency_key, input_payload=payload, result_payload=None,
        error_code=None, cancel_requested=False, created_at=now(), updated_at=now(),
    )
    step = PipelineStepORM(
        id=uuid4(), run_id=run.id, step_key=kind.value, status=StepStatus.QUEUED.value,
        attempt=0, lease_owner=None, lease_expires_at=None, lease_generation=0,
        next_attempt_at=None, external_request_id=None, error_code=None,
        created_at=now(), updated_at=now(),
    )
    session.add_all([run, step])
    await session.commit()
    return run


async def claim_step(
    session: AsyncSession, owner: str, lease_seconds: int
) -> PipelineStepORM | None:
    current = now()
    candidate = await session.scalar(
        select(PipelineStepORM.id)
        .join(PipelineRunORM)
        .where(
            PipelineRunORM.cancel_requested.is_(False),
            or_(
                and_(
                    PipelineStepORM.status.in_([
                        StepStatus.QUEUED.value, StepStatus.RETRY_SCHEDULED.value
                    ]),
                    or_(
                        PipelineStepORM.next_attempt_at.is_(None),
                        PipelineStepORM.next_attempt_at <= current,
                    ),
                ),
                and_(
                    PipelineStepORM.status.in_([
                        StepStatus.CLAIMED.value, StepStatus.RUNNING.value
                    ]),
                    PipelineStepORM.lease_expires_at < current,
                ),
            ),
        )
        .order_by(PipelineStepORM.created_at)
        .limit(1)
    )
    if candidate is None:
        return None
    claimed = await session.scalar(
        update(PipelineStepORM)
        .where(
            PipelineStepORM.id == candidate,
            or_(
                PipelineStepORM.status.in_([
                    StepStatus.QUEUED.value, StepStatus.RETRY_SCHEDULED.value
                ]),
                PipelineStepORM.lease_expires_at < current,
            ),
        )
        .values(
            status=StepStatus.CLAIMED.value,
            lease_owner=owner,
            lease_expires_at=current + timedelta(seconds=lease_seconds),
            lease_generation=PipelineStepORM.lease_generation + 1,
            attempt=PipelineStepORM.attempt + 1,
            updated_at=current,
        )
        .returning(PipelineStepORM)
    )
    if claimed is None:
        await session.rollback()
        return None
    await session.execute(
        update(PipelineRunORM)
        .where(PipelineRunORM.id == claimed.run_id)
        .values(status=RunStatus.RUNNING.value, updated_at=current)
    )
    await session.commit()
    return claimed


async def complete_step(
    session: AsyncSession, step: PipelineStepORM, result: dict[str, Any]
) -> None:
    current = now()
    await session.execute(
        update(PipelineStepORM)
        .where(
            PipelineStepORM.id == step.id,
            PipelineStepORM.lease_generation == step.lease_generation,
        )
        .values(status=StepStatus.SUCCEEDED.value, lease_owner=None, lease_expires_at=None, updated_at=current)
    )
    await session.execute(
        update(PipelineRunORM)
        .where(PipelineRunORM.id == step.run_id)
        .values(status=RunStatus.SUCCEEDED.value, result_payload=result, updated_at=current)
    )
    await session.commit()


async def fail_step(
    session: AsyncSession, step: PipelineStepORM, error_code: str, max_attempts: int
) -> None:
    retry = step.attempt < max_attempts
    step_status = StepStatus.RETRY_SCHEDULED if retry else StepStatus.FAILED
    run_status = RunStatus.QUEUED if retry else RunStatus.FAILED
    current = now()
    await session.execute(
        update(PipelineStepORM)
        .where(
            PipelineStepORM.id == step.id,
            PipelineStepORM.lease_generation == step.lease_generation,
        )
        .values(
            status=step_status.value,
            error_code=error_code,
            next_attempt_at=current + timedelta(seconds=1) if retry else None,
            lease_owner=None,
            lease_expires_at=None,
            updated_at=current,
        )
    )
    await session.execute(
        update(PipelineRunORM)
        .where(PipelineRunORM.id == step.run_id)
        .values(status=run_status.value, error_code=error_code, updated_at=current)
    )
    await session.commit()


async def save_character(
    session: AsyncSession,
    novel_id: UUID,
    name: str,
    description: str | None,
    evidence: str,
    char_start: int,
) -> CharacterORM:
    character = await session.scalar(
        select(CharacterORM).where(CharacterORM.novel_id == novel_id, CharacterORM.name == name)
    )
    if character is None:
        character = CharacterORM(
            id=uuid4(), novel_id=novel_id, name=name, description=description,
            created_at=now(), updated_at=now(),
        )
        session.add(character)
        await session.flush()
    observation = FeatureObservationORM(
        id=uuid4(), character_id=character.id, field_path="appearance.summary",
        value=description or "未描述", evidence_quote=evidence, char_start=char_start,
        char_end=char_start + len(evidence), confidence=1.0, created_at=now(), updated_at=now(),
    )
    session.add(observation)
    await session.commit()
    return character


async def save_image(
    session: AsyncSession,
    character_id: UUID,
    artifact_uri: str,
    prompt: str,
    request_id: str,
) -> GeneratedImageORM:
    existing = await session.scalar(
        select(GeneratedImageORM).where(GeneratedImageORM.provider_request_id == request_id)
    )
    if existing is not None:
        return existing
    image = GeneratedImageORM(
        id=uuid4(), character_id=character_id, artifact_uri=artifact_uri, prompt=prompt,
        provider_request_id=request_id, created_at=now(), updated_at=now(),
    )
    session.add(image)
    await session.commit()
    return image
