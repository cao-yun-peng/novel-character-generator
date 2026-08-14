from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, JsonValue, model_validator

EvalSplit = Literal["dev", "validation", "test"]
EvalTaskType = Literal[
    "observation",
    "entity_link",
    "temporal_binding",
    "conflict",
    "snapshot",
    "expression",
    "agent",
    "image",
    "recovery",
    "security",
]


class EvidenceSpan(BaseModel):
    source_document_version_id: UUID
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    quote: str

    @model_validator(mode="after")
    def validate_span(self) -> "EvidenceSpan":
        if self.char_end <= self.char_start:
            raise ValueError("invalid_evidence_span")
        return self


class EvalDataset(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    version: str
    source: str
    split_strategy: dict[str, JsonValue]
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    frozen: bool = False
    frozen_at: datetime | None = None

    @model_validator(mode="after")
    def validate_freeze_state(self) -> "EvalDataset":
        if self.frozen != (self.frozen_at is not None):
            raise ValueError("eval_dataset_freeze_state_inconsistent")
        return self


class EvalCase(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    eval_dataset_id: UUID
    dataset_version: str
    source_novel_id: UUID | None = None
    source_document_version_id: UUID | None = None
    split_group_key: str
    split: EvalSplit
    task_type: EvalTaskType
    input_refs: list[UUID] = Field(default_factory=list)
    expected_output: JsonValue
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    slice_tags: list[str] = Field(default_factory=list)
    severity: Literal["normal", "important", "critical"] = "normal"
    rubric_version: str
    annotation_status: Literal["single", "double", "adjudicated"]


class EvalRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    eval_dataset_id: UUID
    dataset_version: str
    candidate_config_hash: str = Field(min_length=64, max_length=64)
    baseline_config_hash: str | None = Field(default=None, min_length=64, max_length=64)
    model_versions: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    agent_spec_versions: dict[str, str] = Field(default_factory=dict)
    tool_versions: dict[str, str] = Field(default_factory=dict)
    schema_versions: dict[str, str] = Field(default_factory=dict)
    workflow_profile_version: str | None = None
    grader_bundle_version: str
    random_seeds: list[int]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    total_tokens: int = Field(default=0, ge=0)
    total_latency_ms: int = Field(default=0, ge=0)
    total_cost: Decimal = Field(default=Decimal("0"), ge=0)


class GraderVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    grader_key: str
    version: str
    grader_kind: Literal["deterministic", "model", "human"]
    definition: dict[str, JsonValue]
    model_provider: str | None = None
    model_name: str | None = None
    model_revision: str | None = None
    prompt_version: str | None = None
    rubric_version: str
    sampling_parameters: dict[str, JsonValue] | None = None
    content_hash: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_model_grader(self) -> "GraderVersion":
        if self.grader_kind == "model" and (
            self.model_provider is None
            or self.model_name is None
            or self.model_revision is None
            or self.prompt_version is None
            or self.sampling_parameters is None
        ):
            raise ValueError("model_grader_provenance_required")
        return self


class EvalResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    eval_run_id: UUID
    eval_case_id: UUID
    grader_version_id: UUID
    raw_output_artifact_id: UUID | None = None
    scores: dict[str, JsonValue]
    score: float | None = None
    passed: bool
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)
    failure_reason: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
