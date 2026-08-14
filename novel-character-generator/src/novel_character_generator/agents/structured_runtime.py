import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import cast

from pydantic import BaseModel, JsonValue, ValidationError

from novel_character_generator.application.ports.agent_runtime import (
    PERMISSION_RANK,
    AgentContextPacket,
    AgentHistoryEntry,
    AgentLimitReached,
    AgentModelClient,
    AgentRunResult,
    AgentSpec,
    ApprovalRequest,
    LimitReason,
    TokenUsage,
    ToolCallRequest,
    ToolPermission,
    ToolSpec,
)
from novel_character_generator.settings import Settings, get_settings

ToolHandler = Callable[[BaseModel], Awaitable[BaseModel]]


class AgentRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RegisteredTool:
    def __init__(
        self,
        *,
        spec: ToolSpec,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        handler: ToolHandler,
    ) -> None:
        self.spec = spec
        self.input_model = input_model
        self.output_model = output_model
        self.handler = handler

    async def execute(self, arguments: dict[str, JsonValue]) -> JsonValue:
        try:
            tool_input = self.input_model.model_validate(arguments)
        except ValidationError as error:
            raise AgentRuntimeError("tool_input_validation_failed") from error
        try:
            output = await asyncio.wait_for(
                self.handler(tool_input), timeout=self.spec.timeout_seconds
            )
        except TimeoutError as error:
            raise AgentRuntimeError("tool_timeout") from error
        try:
            validated = self.output_model.model_validate(output)
        except ValidationError as error:
            raise AgentRuntimeError("tool_output_validation_failed") from error
        return cast(JsonValue, validated.model_dump(mode="json"))


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        if tool.spec.name in self._tools:
            raise ValueError("tool_already_registered")
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as error:
            raise AgentRuntimeError("tool_not_registered") from error


class StructuredCallAgentRuntime:
    def __init__(
        self,
        *,
        model: AgentModelClient,
        tools: ToolRegistry,
        output_schemas: dict[str, type[BaseModel]],
        settings: Settings | None = None,
    ) -> None:
        self.model = model
        self.tools = tools
        self.output_schemas = output_schemas
        self.settings = settings or get_settings()

    async def run(
        self,
        *,
        spec: AgentSpec,
        context: AgentContextPacket,
        permission: ToolPermission,
    ) -> AgentRunResult:
        self._validate_spec(spec)
        available_tools = self._available_tools(spec, context)
        history: list[AgentHistoryEntry] = []
        input_tokens = 0
        output_tokens = 0
        cost = Decimal("0")
        tool_call_count = 0
        seen_call_ids: set[str] = set()
        try:
            async with asyncio.timeout(spec.deadline_seconds):
                for turn_number in range(1, spec.max_turns + 1):
                    turn = await self.model.generate_turn(
                        spec=spec,
                        context=context,
                        history=history,
                        tools=[tool.spec for tool in available_tools],
                    )
                    input_tokens += turn.usage.input_tokens
                    output_tokens += turn.usage.output_tokens
                    cost += turn.usage.cost
                    usage = TokenUsage(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                    )
                    if turn.usage.input_tokens > context.token_budget:
                        return self._limit_result(
                            history=history,
                            usage=usage,
                            reason="token_budget",
                            limit=context.token_budget,
                            observed=turn.usage.input_tokens,
                        )
                    if cost > spec.max_cost:
                        return self._limit_result(
                            history=history,
                            usage=usage,
                            reason="cost",
                            limit=spec.max_cost,
                            observed=cost,
                        )
                    entry = AgentHistoryEntry(
                        turn_number=turn_number,
                        output=turn.output,
                        tool_calls=turn.tool_calls,
                        usage=turn.usage,
                    )
                    if turn.output is not None:
                        entry.output = self._validate_output(spec.output_schema, turn.output)
                        history.append(entry)
                        return AgentRunResult(
                            status="completed",
                            output=entry.output,
                            history=history,
                            total_usage=usage,
                            stop_reason=turn.stop_reason or "completed",
                        )

                    requested = self._preflight_tool_calls(
                        turn.tool_calls,
                        spec=spec,
                        context=context,
                        permission=permission,
                        seen_call_ids=seen_call_ids,
                    )
                    next_count = tool_call_count + len(requested)
                    if next_count > spec.max_tool_calls:
                        return self._limit_result(
                            history=history,
                            usage=usage,
                            reason="tool_calls",
                            limit=spec.max_tool_calls,
                            observed=next_count,
                        )
                    estimated_tool_cost = sum(
                        (tool.spec.estimated_cost or Decimal("0") for _, tool in requested),
                        start=Decimal("0"),
                    )
                    if cost + estimated_tool_cost > spec.max_cost:
                        return self._limit_result(
                            history=history,
                            usage=usage,
                            reason="cost",
                            limit=spec.max_cost,
                            observed=cost + estimated_tool_cost,
                        )
                    approval = self._approval_request(requested)
                    if approval is not None:
                        history.append(entry)
                        return AgentRunResult(
                            status="approval_required",
                            approval_request=approval,
                            history=history,
                            total_usage=usage,
                            stop_reason="approval_required",
                        )
                    for call, tool in requested:
                        started = perf_counter()
                        entry.tool_results[call.call_id] = await tool.execute(call.arguments)
                        entry.tool_durations_ms[call.call_id] = round(
                            (perf_counter() - started) * 1_000
                        )
                        seen_call_ids.add(call.call_id)
                    tool_call_count = next_count
                    history.append(entry)
        except TimeoutError:
            usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )
            return self._limit_result(
                history=history,
                usage=usage,
                reason="deadline",
                limit=spec.deadline_seconds,
                observed=spec.deadline_seconds,
            )
        usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens, cost=cost)
        return self._limit_result(
            history=history,
            usage=usage,
            reason="turns",
            limit=spec.max_turns,
            observed=spec.max_turns,
        )

    def _validate_spec(self, spec: AgentSpec) -> None:
        if not spec.enabled:
            raise AgentRuntimeError("agent_disabled")
        if spec.max_turns > self.settings.agent_max_turns_default:
            raise AgentRuntimeError("agent_turn_limit_exceeds_runtime_policy")
        if spec.max_tool_calls > self.settings.agent_max_tool_calls_default:
            raise AgentRuntimeError("agent_tool_limit_exceeds_runtime_policy")
        if spec.max_cost > self.settings.agent_max_cost_default:
            raise AgentRuntimeError("agent_cost_limit_exceeds_runtime_policy")
        if spec.deadline_seconds > self.settings.agent_deadline_seconds_default:
            raise AgentRuntimeError("agent_deadline_exceeds_runtime_policy")
        if spec.output_schema not in self.output_schemas:
            raise AgentRuntimeError("agent_output_schema_not_registered")

    def _available_tools(
        self, spec: AgentSpec, context: AgentContextPacket
    ) -> list[RegisteredTool]:
        context_tools = set(context.available_tool_names)
        return [self.tools.get(name) for name in spec.allowed_tools if name in context_tools]

    def _preflight_tool_calls(
        self,
        calls: list[ToolCallRequest],
        *,
        spec: AgentSpec,
        context: AgentContextPacket,
        permission: ToolPermission,
        seen_call_ids: set[str],
    ) -> list[tuple[ToolCallRequest, RegisteredTool]]:
        allowed = set(spec.allowed_tools) & set(context.available_tool_names)
        requested: list[tuple[ToolCallRequest, RegisteredTool]] = []
        current_ids: set[str] = set()
        for call in calls:
            if call.call_id in seen_call_ids or call.call_id in current_ids:
                raise AgentRuntimeError("duplicate_tool_call_id")
            current_ids.add(call.call_id)
            if call.tool_name not in allowed:
                raise AgentRuntimeError("tool_not_allowed")
            tool = self.tools.get(call.tool_name)
            required = tool.spec.required_permission
            if required is not None and PERMISSION_RANK[permission] < PERMISSION_RANK[required]:
                raise AgentRuntimeError("tool_permission_denied")
            requested.append((call, tool))
        return requested

    def _approval_request(
        self, requested: list[tuple[ToolCallRequest, RegisteredTool]]
    ) -> ApprovalRequest | None:
        for call, tool in requested:
            if tool.spec.requires_approval:
                return ApprovalRequest(
                    tool_call=call,
                    action={"tool": call.tool_name, "arguments": call.arguments},
                    estimated_cost=tool.spec.estimated_cost,
                    options=["approve", "reject", "modify", "defer"],
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                )
        return None

    def _validate_output(self, schema_name: str, output: JsonValue) -> JsonValue:
        try:
            validated = self.output_schemas[schema_name].model_validate(output)
        except ValidationError as error:
            raise AgentRuntimeError("agent_output_validation_failed") from error
        return cast(JsonValue, validated.model_dump(mode="json"))

    @staticmethod
    def _limit_result(
        *,
        history: list[AgentHistoryEntry],
        usage: TokenUsage,
        reason: str,
        limit: int | Decimal,
        observed: int | Decimal,
    ) -> AgentRunResult:
        limit_reached = AgentLimitReached(
            reason=cast(LimitReason, reason),
            limit=limit,
            observed=observed,
        )
        return AgentRunResult(
            status="limit_reached",
            limit_reached=limit_reached,
            history=history,
            total_usage=usage,
            stop_reason=f"limit:{reason}",
        )
