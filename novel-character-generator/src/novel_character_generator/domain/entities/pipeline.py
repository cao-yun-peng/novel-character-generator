from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class StepStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    WAITING_EXTERNAL = "waiting_external"
    RETRY_SCHEDULED = "retry_scheduled"
    PAUSED_FOR_REVIEW = "paused_for_review"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"


ALLOWED_STEP_TRANSITIONS: dict[StepStatus, frozenset[StepStatus]] = {
    StepStatus.QUEUED: frozenset({StepStatus.CLAIMED, StepStatus.CANCELLED}),
    StepStatus.CLAIMED: frozenset({StepStatus.RUNNING, StepStatus.RETRY_SCHEDULED}),
    StepStatus.RUNNING: frozenset(
        {
            StepStatus.WAITING_EXTERNAL,
            StepStatus.RETRY_SCHEDULED,
            StepStatus.PAUSED_FOR_REVIEW,
            StepStatus.WAITING_APPROVAL,
            StepStatus.SUCCEEDED,
            StepStatus.CANCELLED,
            StepStatus.FAILED,
        }
    ),
    StepStatus.WAITING_EXTERNAL: frozenset(
        {StepStatus.RUNNING, StepStatus.RETRY_SCHEDULED, StepStatus.CANCELLED, StepStatus.FAILED}
    ),
    StepStatus.RETRY_SCHEDULED: frozenset({StepStatus.CLAIMED, StepStatus.CANCELLED}),
    StepStatus.PAUSED_FOR_REVIEW: frozenset(
        {StepStatus.RUNNING, StepStatus.CANCELLED, StepStatus.FAILED}
    ),
    StepStatus.WAITING_APPROVAL: frozenset(
        {StepStatus.QUEUED, StepStatus.CANCELLED, StepStatus.FAILED}
    ),
    StepStatus.SUCCEEDED: frozenset(),
    StepStatus.CANCELLED: frozenset(),
    StepStatus.FAILED: frozenset({StepStatus.RETRY_SCHEDULED}),
}


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PipelineRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    novel_id: UUID
    run_type: str
    status: RunStatus = RunStatus.QUEUED
    idempotency_key: str
    cancel_requested: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PipelineStep(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    step_key: str
    status: StepStatus = StepStatus.QUEUED
    attempt: int = Field(default=0, ge=0)
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    lease_generation: int = Field(default=0, ge=0)
    heartbeat_at: datetime | None = None

    def can_transition_to(self, target: StepStatus) -> bool:
        return target in ALLOWED_STEP_TRANSITIONS[self.status]
