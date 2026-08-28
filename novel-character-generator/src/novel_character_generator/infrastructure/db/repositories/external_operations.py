from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.domain.entities.pipeline import (
    ALLOWED_EXTERNAL_OPERATION_TRANSITIONS,
    ExternalOperationState,
)
from novel_character_generator.infrastructure.db.orm import ExternalOperationORM


class ExternalOperationConflict(RuntimeError):
    pass


class ExternalOperationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def prepare(
        self,
        *,
        run_id: UUID,
        step_id: UUID,
        provider: str,
        operation_kind: str,
        idempotency_key: str,
        request_fingerprint: str,
        lease_generation: int,
    ) -> ExternalOperationORM:
        existing = await self.session.scalar(
            select(ExternalOperationORM).where(
                ExternalOperationORM.provider == provider,
                ExternalOperationORM.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise ExternalOperationConflict("external_operation_idempotency_conflict")
            return existing
        now = datetime.now(UTC)
        operation = ExternalOperationORM(
            id=uuid4(),
            pipeline_step_id=step_id,
            run_id=run_id,
            provider=provider,
            operation_kind=operation_kind,
            idempotency_key=idempotency_key,
            request_hash=request_fingerprint,
            request_fingerprint=request_fingerprint,
            status=ExternalOperationState.PREPARED.value,
            lease_generation=lease_generation,
            attempt=0,
            provider_request_id=None,
            result_refs=[],
            response_hash=None,
            artifact_id=None,
            submitted_at=None,
            completed_at=None,
            last_reconciled_at=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(operation)
        await self.session.flush()
        return operation

    async def transition(
        self,
        operation_id: UUID,
        *,
        target: ExternalOperationState,
        expected_generation: int,
        provider_request_id: str | None = None,
        result_refs: list[str] | None = None,
        response_hash: str | None = None,
    ) -> ExternalOperationORM:
        operation = await self.session.get(ExternalOperationORM, operation_id)
        if operation is None:
            raise ValueError("external_operation_not_found")
        current = ExternalOperationState(operation.status)
        if target not in ALLOWED_EXTERNAL_OPERATION_TRANSITIONS[current]:
            raise ValueError("external_operation_transition_not_allowed")
        now = datetime.now(UTC)
        values: dict[str, object] = {"status": target.value, "updated_at": now}
        if target == ExternalOperationState.SUBMITTING:
            values["attempt"] = operation.attempt + 1
        if target == ExternalOperationState.SUBMITTED:
            values["submitted_at"] = now
            values["provider_request_id"] = provider_request_id
            if result_refs is not None:
                values["result_refs"] = result_refs
        if target in {
            ExternalOperationState.SUCCEEDED,
            ExternalOperationState.FAILED,
            ExternalOperationState.CANCELLED,
        }:
            values["completed_at"] = now
        if target == ExternalOperationState.RECONCILING:
            values["last_reconciled_at"] = now
        if response_hash is not None:
            values["response_hash"] = response_hash
        updated_id = await self.session.scalar(
            update(ExternalOperationORM)
            .where(
                ExternalOperationORM.id == operation_id,
                ExternalOperationORM.status == current.value,
                ExternalOperationORM.lease_generation == expected_generation,
            )
            .values(**values)
            .returning(ExternalOperationORM.id)
        )
        if updated_id is None:
            raise ExternalOperationConflict("external_operation_fencing_conflict")
        await self.session.flush()
        return await self.session.get_one(ExternalOperationORM, operation_id)

    async def list_for_run(self, run_id: UUID) -> list[ExternalOperationORM]:
        operations = await self.session.scalars(
            select(ExternalOperationORM)
            .where(ExternalOperationORM.run_id == run_id)
            .order_by(ExternalOperationORM.created_at)
        )
        return list(operations)
