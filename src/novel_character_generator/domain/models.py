from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RunKind(StrEnum):
    EXTRACT = "extract"
    IMAGE = "image"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


CLAIMABLE_STEP_STATUSES = (StepStatus.QUEUED, StepStatus.RETRY_SCHEDULED)


class Novel(BaseModel):
    id: UUID
    title: str
    content_sha256: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Character(BaseModel):
    id: UUID
    novel_id: UUID
    name: str
    description: str | None = None


class FeatureObservation(BaseModel):
    id: UUID
    character_id: UUID
    field_path: str
    value: str
    evidence_quote: str
    char_start: int
    char_end: int
    confidence: float = Field(ge=0, le=1)


class GeneratedImage(BaseModel):
    id: UUID
    character_id: UUID
    artifact_uri: str
    prompt: str
    provider_request_id: str


class PipelineRun(BaseModel):
    id: UUID
    novel_id: UUID
    kind: RunKind
    status: RunStatus
    idempotency_key: str
    input_payload: dict[str, Any]
    result_payload: dict[str, Any] | None = None
    error_code: str | None = None
    cancel_requested: bool = False


class PipelineStep(BaseModel):
    id: UUID
    run_id: UUID
    step_key: str
    status: StepStatus
    attempt: int
    lease_owner: str | None = None
    lease_generation: int = 0
    external_request_id: str | None = None
