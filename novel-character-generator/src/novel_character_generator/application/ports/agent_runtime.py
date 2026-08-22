from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue, model_validator


class ToolPermission(StrEnum):
    READ = "read"
    PROPOSE = "propose"
    EXECUTE = "execute"
    ADMIN = "admin"


PERMISSION_RANK: dict[ToolPermission, int] = {
    ToolPermission.READ: 0,
    ToolPermission.PROPOSE: 1,
    ToolPermission.EXECUTE: 2,
    ToolPermission.ADMIN: 3,
}


class AgentSpec(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1)
    model_policy: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=100)
    allowed_tools: list[str] = Field(default_factory=list)
    output_schema: str = Field(min_length=1, max_length=255)
    max_turns: int = Field(ge=1)
    max_tool_calls: int = Field(ge=0)
    max_cost: Decimal = Field(ge=0)
    deadline_seconds: int = Field(ge=1)
    approval_policy: str = Field(min_length=1, max_length=100)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_unique_tools(self) -> "AgentSpec":
        if len(self.allowed_tools) != len(set(self.allowed_tools)):
            raise ValueError("agent_allowed_tools_must_be_unique")
        return self


class ToolSpec(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    input_schema: str = Field(min_length=1, max_length=255)
    output_schema: str = Field(min_length=1, max_length=255)
    side_effect: Literal["none", "reversible", "irreversible"]
    idempotency: Literal["not_required", "supported", "required"]
    required_permission: ToolPermission | None = None
    requires_approval: bool
    timeout_seconds: int = Field(ge=1)
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    error_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_side_effect_policy(self) -> "ToolSpec":
        if self.side_effect == "irreversible" and not self.requires_approval:
            raise ValueError("irreversible_tool_requires_approval")
        if self.side_effect == "irreversible" and self.idempotency != "required":
            raise ValueError("irreversible_tool_requires_idempotency")
        return self


class AgentContextPacket(BaseModel):
    objective: str
    current_chunk: dict[str, JsonValue] | None = None
    related_characters: list[dict[str, JsonValue]] = Field(default_factory=list)
    relevant_observations: list[dict[str, JsonValue]] = Field(default_factory=list)
    unresolved_questions: list[dict[str, JsonValue]] = Field(default_factory=list)
    policy_constraints: list[str] = Field(default_factory=list)
    available_tool_names: list[str] = Field(default_factory=list)
    token_budget: int = Field(gt=0)
    context_hash: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_unique_tools(self) -> "AgentContextPacket":
        if len(self.available_tool_names) != len(set(self.available_tool_names)):
            raise ValueError("context_tool_names_must_be_unique")
        return self


class TokenUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost: Decimal = Field(default=Decimal("0"), ge=0)


class ToolCallRequest(BaseModel):
    call_id: str = Field(min_length=1, max_length=255)
    tool_name: str = Field(min_length=1, max_length=255)
    arguments: dict[str, JsonValue]


class AgentHistoryEntry(BaseModel):
    turn_number: int = Field(ge=1)
    output: JsonValue | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    tool_results: dict[str, JsonValue] = Field(default_factory=dict)
    tool_durations_ms: dict[str, int] = Field(default_factory=dict)
    usage: TokenUsage = Field(default_factory=TokenUsage)


class AgentModelTurn(BaseModel):
    output: JsonValue | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    stop_reason: str | None = None

    @model_validator(mode="after")
    def validate_content(self) -> "AgentModelTurn":
        if self.output is None and not self.tool_calls:
            raise ValueError("agent_turn_requires_output_or_tool_call")
        if self.output is not None and self.tool_calls:
            raise ValueError("agent_turn_cannot_mix_output_and_tool_calls")
        return self


class ApprovalRequest(BaseModel):
    tool_call: ToolCallRequest
    action: dict[str, JsonValue]
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    opposing_evidence_ids: list[UUID] = Field(default_factory=list)
    estimated_cost: Decimal | None = None
    options: list[Literal["approve", "reject", "modify", "defer"]]
    expires_at: datetime


LimitReason = Literal["turns", "tool_calls", "cost", "deadline", "token_budget"]


class AgentLimitReached(BaseModel):
    reason: LimitReason
    limit: int | Decimal
    observed: int | Decimal


class AgentRunResult(BaseModel):
    status: Literal["completed", "approval_required", "limit_reached"]
    output: JsonValue | None = None
    approval_request: ApprovalRequest | None = None
    limit_reached: AgentLimitReached | None = None
    history: list[AgentHistoryEntry]
    total_usage: TokenUsage
    stop_reason: str

    @model_validator(mode="after")
    def validate_status_payload(self) -> "AgentRunResult":
        if self.status == "completed" and self.output is None:
            raise ValueError("completed_agent_run_requires_output")
        if self.status == "approval_required" and self.approval_request is None:
            raise ValueError("approval_agent_run_requires_request")
        if self.status == "limit_reached" and self.limit_reached is None:
            raise ValueError("limited_agent_run_requires_limit")
        return self


class AgentModelClient(Protocol):
    async def generate_turn(
        self,
        *,
        spec: AgentSpec,
        context: AgentContextPacket,
        history: list[AgentHistoryEntry],
        tools: list[ToolSpec],
    ) -> AgentModelTurn: ...


class AgentRuntime(Protocol):
    async def run(
        self,
        *,
        spec: AgentSpec,
        context: AgentContextPacket,
        permission: ToolPermission,
    ) -> AgentRunResult: ...
