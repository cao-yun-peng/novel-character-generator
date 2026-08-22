import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest
from typing import Literal
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.agent_runtime import ApprovalRequest
from novel_character_generator.infrastructure.db.orm import (
    AgentRunORM,
    HumanApprovalORM,
    PipelineRunORM,
    PipelineStepORM,
)
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event

ApprovalDecision = Literal["approve", "reject", "modify", "defer"]


class ApprovalConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class CreatedApproval:
    approval: HumanApprovalORM
    recovery_token: str


@dataclass(frozen=True)
class ApprovalPage:
    items: list[HumanApprovalORM]
    next_cursor: UUID | None


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_request(
        self,
        *,
        pipeline_step_id: UUID,
        expected_generation: int,
        request: ApprovalRequest,
        approval_type: str = "agent_tool",
        requested_by_agent_run_id: UUID | None = None,
    ) -> CreatedApproval:
        step = await self.session.get(PipelineStepORM, pipeline_step_id)
        if step is None:
            raise ValueError("pipeline_step_not_found")
        if requested_by_agent_run_id is not None:
            agent_run = await self.session.get(AgentRunORM, requested_by_agent_run_id)
            if agent_run is None or agent_run.pipeline_step_id != step.id:
                raise ValueError("agent_run_step_mismatch")
        action = request.action
        action_hash = _canonical_hash(action)
        existing = await self.session.scalar(
            select(HumanApprovalORM.id).where(HumanApprovalORM.action_hash == action_hash)
        )
        if existing is not None:
            raise ApprovalConflict("approval_action_already_exists")
        recovery_token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        approval = HumanApprovalORM(
            id=uuid4(),
            pipeline_step_id=step.id,
            requested_by_agent_run_id=requested_by_agent_run_id,
            approval_type=approval_type,
            subject_type="tool_call",
            subject_id=step.id,
            lease_generation=expected_generation,
            revision=1,
            action_hash=action_hash,
            action=action,
            supporting_evidence_ids=[str(item) for item in request.supporting_evidence_ids],
            opposing_evidence_ids=[str(item) for item in request.opposing_evidence_ids],
            estimated_cost=(
                {"amount": str(request.estimated_cost), "currency": "USD"}
                if request.estimated_cost is not None
                else None
            ),
            status="pending",
            decision=None,
            modifications=None,
            resolved_by=None,
            expires_at=request.expires_at,
            resolved_at=None,
            recovery_token_hash=sha256(recovery_token.encode()).hexdigest(),
            decision_payload_hash=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(approval)
        updated_id = await self.session.scalar(
            update(PipelineStepORM)
            .where(
                PipelineStepORM.id == step.id,
                PipelineStepORM.status.in_(("running", "waiting_external")),
                PipelineStepORM.lease_generation == expected_generation,
            )
            .values(
                status="waiting_approval",
                lease_owner=None,
                lease_expires_at=None,
                updated_at=now,
            )
            .returning(PipelineStepORM.id)
        )
        if updated_id is None:
            await self.session.rollback()
            raise ApprovalConflict("approval_step_fencing_conflict")
        await append_run_event(
            self.session,
            run_id=step.run_id,
            event_type="approval.requested",
            payload={
                "approval_id": str(approval.id),
                "step_id": str(step.id),
                "approval_type": approval_type,
                "revision": approval.revision,
            },
        )
        await self.session.commit()
        return CreatedApproval(approval=approval, recovery_token=recovery_token)

    async def list_pending(
        self,
        *,
        status: str | None,
        approval_type: str | None,
        cursor: UUID | None,
        limit: int,
    ) -> ApprovalPage:
        query = select(HumanApprovalORM)
        if status is not None:
            query = query.where(HumanApprovalORM.status == status)
        if approval_type is not None:
            query = query.where(HumanApprovalORM.approval_type == approval_type)
        if cursor is not None:
            cursor_row = await self.session.get(HumanApprovalORM, cursor)
            if cursor_row is None:
                raise ValueError("approval_cursor_not_found")
            query = query.where(
                or_(
                    HumanApprovalORM.created_at > cursor_row.created_at,
                    and_(
                        HumanApprovalORM.created_at == cursor_row.created_at,
                        HumanApprovalORM.id > cursor_row.id,
                    ),
                )
            )
        rows = list(
            await self.session.scalars(
                query.order_by(HumanApprovalORM.created_at, HumanApprovalORM.id).limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        return ApprovalPage(
            items=items,
            next_cursor=items[-1].id if has_more and items else None,
        )

    async def resolve(
        self,
        approval_id: UUID,
        *,
        decision: ApprovalDecision,
        expected_revision: int,
        recovery_token: str | None,
        resolved_by: str,
        modifications: dict[str, JsonValue] | None = None,
        defer_until: datetime | None = None,
    ) -> HumanApprovalORM:
        approval = await self.session.get(HumanApprovalORM, approval_id)
        if approval is None:
            raise ValueError("approval_not_found")
        if approval.status != "pending":
            raise ApprovalConflict("approval_already_resolved")
        if approval.pipeline_step_id is None:
            raise ApprovalConflict("approval_has_no_resumable_step")
        if approval.revision != expected_revision:
            raise ApprovalConflict("approval_revision_conflict")
        if recovery_token is not None:
            supplied_hash = sha256(recovery_token.encode()).hexdigest()
            if not compare_digest(supplied_hash, approval.recovery_token_hash):
                raise ApprovalConflict("approval_recovery_token_invalid")
        now = datetime.now(UTC)
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            await self.session.execute(
                update(HumanApprovalORM)
                .where(
                    HumanApprovalORM.id == approval.id,
                    HumanApprovalORM.status == "pending",
                    HumanApprovalORM.revision == expected_revision,
                )
                .values(status="expired", revision=expected_revision + 1, updated_at=now)
            )
            await self.session.commit()
            raise ApprovalConflict("approval_expired")
        if decision == "modify" and modifications is None:
            raise ValueError("approval_modifications_required")
        if decision == "defer" and (defer_until is None or defer_until <= now):
            raise ValueError("approval_defer_until_required")

        decision_payload = {
            "decision": decision,
            "modifications": modifications,
            "defer_until": defer_until.isoformat() if defer_until else None,
        }
        next_status = {
            "approve": "approved",
            "reject": "rejected",
            "modify": "modified",
            "defer": "pending",
        }[decision]
        values: dict[str, object] = {
            "status": next_status,
            "decision": decision,
            "modifications": modifications,
            "resolved_by": None if decision == "defer" else resolved_by,
            "resolved_at": None if decision == "defer" else now,
            "decision_payload_hash": _canonical_hash(decision_payload),
            "revision": expected_revision + 1,
            "updated_at": now,
        }
        if defer_until is not None:
            values["expires_at"] = defer_until
        updated_id = await self.session.scalar(
            update(HumanApprovalORM)
            .where(
                HumanApprovalORM.id == approval.id,
                HumanApprovalORM.status == "pending",
                HumanApprovalORM.revision == expected_revision,
            )
            .values(**values)
            .returning(HumanApprovalORM.id)
        )
        if updated_id is None:
            await self.session.rollback()
            raise ApprovalConflict("approval_revision_conflict")

        step = await self.session.get(PipelineStepORM, approval.pipeline_step_id)
        if step is None:
            await self.session.rollback()
            raise ValueError("pipeline_step_not_found")
        if decision != "defer":
            step_status = "cancelled" if decision == "reject" else "queued"
            step_updated = await self.session.scalar(
                update(PipelineStepORM)
                .where(
                    PipelineStepORM.id == step.id,
                    PipelineStepORM.status == "waiting_approval",
                    PipelineStepORM.lease_generation == approval.lease_generation,
                )
                .values(
                    status=step_status,
                    next_attempt_at=now if step_status == "queued" else None,
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
                .returning(PipelineStepORM.id)
            )
            if step_updated is None:
                await self.session.rollback()
                raise ApprovalConflict("approval_step_fencing_conflict")
            run = await self.session.get(PipelineRunORM, step.run_id)
            if run is None:
                await self.session.rollback()
                raise ValueError("pipeline_run_not_found")
            run.status = "cancelled" if decision == "reject" else "queued"
            run.completed_at = now if decision == "reject" else None
            run.updated_at = now
        await append_run_event(
            self.session,
            run_id=step.run_id,
            event_type="approval.deferred" if decision == "defer" else "approval.resolved",
            payload={
                "approval_id": str(approval.id),
                "step_id": str(step.id),
                "decision": decision,
                "revision": expected_revision + 1,
            },
        )
        await self.session.commit()
        return await self.session.get_one(HumanApprovalORM, approval.id)
