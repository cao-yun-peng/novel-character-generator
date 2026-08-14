from decimal import Decimal

import pytest
from pydantic import BaseModel

from novel_character_generator.agents.structured_runtime import (
    AgentRuntimeError,
    RegisteredTool,
    StructuredCallAgentRuntime,
    ToolRegistry,
)
from novel_character_generator.application.ports.agent_runtime import (
    AgentContextPacket,
    AgentHistoryEntry,
    AgentModelTurn,
    AgentSpec,
    TokenUsage,
    ToolCallRequest,
    ToolPermission,
    ToolSpec,
)
from novel_character_generator.settings import Settings


class EchoInput(BaseModel):
    value: str


class EchoOutput(BaseModel):
    value: str


class FinalOutput(BaseModel):
    answer: str


class SequenceModel:
    def __init__(self, turns: list[AgentModelTurn]) -> None:
        self.turns = turns
        self.histories: list[list[AgentHistoryEntry]] = []

    async def generate_turn(
        self,
        *,
        spec: AgentSpec,
        context: AgentContextPacket,
        history: list[AgentHistoryEntry],
        tools: list[ToolSpec],
    ) -> AgentModelTurn:
        del spec, context, tools
        self.histories.append(history.copy())
        return self.turns.pop(0)


def agent_spec(*, allowed_tools: list[str], max_cost: str = "1") -> AgentSpec:
    return AgentSpec(
        agent_id="test-agent",
        version="v1",
        objective="Return a validated answer",
        model_policy="test-model",
        prompt_version="prompt-v1",
        allowed_tools=allowed_tools,
        output_schema="FinalOutput",
        max_turns=3,
        max_tool_calls=4,
        max_cost=Decimal(max_cost),
        deadline_seconds=30,
        approval_policy="write_requires_approval",
    )


def context(*tools: str) -> AgentContextPacket:
    return AgentContextPacket(
        objective="test",
        available_tool_names=list(tools),
        token_budget=1_000,
        context_hash="c" * 64,
    )


def runtime_settings() -> Settings:
    return Settings(
        agent_max_turns_default=3,
        agent_max_tool_calls_default=4,
        agent_max_cost_default=Decimal("10"),
        agent_deadline_seconds_default=30,
    )


def registered_tool(
    *,
    name: str,
    handler,
    permission: ToolPermission = ToolPermission.READ,
    side_effect: str = "none",
    requires_approval: bool = False,
) -> RegisteredTool:
    return RegisteredTool(
        spec=ToolSpec(
            name=name,
            version="v1",
            description="A strongly typed test tool",
            input_schema="EchoInput",
            output_schema="EchoOutput",
            side_effect=side_effect,
            idempotency="required" if side_effect == "irreversible" else "not_required",
            required_permission=permission,
            requires_approval=requires_approval,
            timeout_seconds=1,
            estimated_cost=Decimal("0.1"),
        ),
        input_model=EchoInput,
        output_model=EchoOutput,
        handler=handler,
    )


@pytest.mark.asyncio
async def test_runtime_executes_typed_tool_then_validates_final_output() -> None:
    async def echo(payload: BaseModel) -> BaseModel:
        validated = EchoInput.model_validate(payload)
        return EchoOutput(value=validated.value)

    registry = ToolRegistry()
    registry.register(registered_tool(name="echo", handler=echo))
    model = SequenceModel(
        [
            AgentModelTurn(
                tool_calls=[
                    ToolCallRequest(
                        call_id="call-1", tool_name="echo", arguments={"value": "ok"}
                    )
                ],
                usage=TokenUsage(input_tokens=10, output_tokens=3, cost=Decimal("0.01")),
            ),
            AgentModelTurn(
                output={"answer": "done"},
                usage=TokenUsage(input_tokens=5, output_tokens=2, cost=Decimal("0.01")),
            ),
        ]
    )
    runtime = StructuredCallAgentRuntime(
        model=model,
        tools=registry,
        output_schemas={"FinalOutput": FinalOutput},
        settings=runtime_settings(),
    )

    result = await runtime.run(
        spec=agent_spec(allowed_tools=["echo"]),
        context=context("echo"),
        permission=ToolPermission.READ,
    )

    assert result.status == "completed"
    assert result.output == {"answer": "done"}
    assert result.history[0].tool_results == {"call-1": {"value": "ok"}}
    assert result.total_usage.input_tokens == 15


@pytest.mark.asyncio
async def test_runtime_rejects_tool_permission_escalation() -> None:
    async def execute(payload: BaseModel) -> BaseModel:
        return EchoOutput.model_validate(payload)

    registry = ToolRegistry()
    registry.register(
        registered_tool(
            name="execute",
            handler=execute,
            permission=ToolPermission.EXECUTE,
            side_effect="reversible",
        )
    )
    model = SequenceModel(
        [
            AgentModelTurn(
                tool_calls=[
                    ToolCallRequest(
                        call_id="call-1",
                        tool_name="execute",
                        arguments={"value": "unsafe"},
                    )
                ]
            )
        ]
    )
    runtime = StructuredCallAgentRuntime(
        model=model,
        tools=registry,
        output_schemas={"FinalOutput": FinalOutput},
        settings=runtime_settings(),
    )

    with pytest.raises(AgentRuntimeError, match="tool_permission_denied"):
        await runtime.run(
            spec=agent_spec(allowed_tools=["execute"]),
            context=context("execute"),
            permission=ToolPermission.READ,
        )


@pytest.mark.asyncio
async def test_approval_preflight_prevents_partial_side_effects() -> None:
    calls = 0

    async def handler(payload: BaseModel) -> BaseModel:
        nonlocal calls
        calls += 1
        return EchoOutput.model_validate(payload)

    registry = ToolRegistry()
    registry.register(registered_tool(name="read", handler=handler))
    registry.register(
        registered_tool(
            name="publish",
            handler=handler,
            permission=ToolPermission.ADMIN,
            side_effect="irreversible",
            requires_approval=True,
        )
    )
    model = SequenceModel(
        [
            AgentModelTurn(
                tool_calls=[
                    ToolCallRequest(
                        call_id="call-read", tool_name="read", arguments={"value": "safe"}
                    ),
                    ToolCallRequest(
                        call_id="call-publish",
                        tool_name="publish",
                        arguments={"value": "expensive"},
                    ),
                ]
            )
        ]
    )
    runtime = StructuredCallAgentRuntime(
        model=model,
        tools=registry,
        output_schemas={"FinalOutput": FinalOutput},
        settings=runtime_settings(),
    )

    result = await runtime.run(
        spec=agent_spec(allowed_tools=["read", "publish"]),
        context=context("read", "publish"),
        permission=ToolPermission.ADMIN,
    )

    assert result.status == "approval_required"
    assert result.approval_request is not None
    assert result.approval_request.tool_call.tool_name == "publish"
    assert calls == 0


@pytest.mark.asyncio
async def test_runtime_returns_structured_cost_limit() -> None:
    model = SequenceModel(
        [
            AgentModelTurn(
                output={"answer": "too expensive"},
                usage=TokenUsage(cost=Decimal("2")),
            )
        ]
    )
    runtime = StructuredCallAgentRuntime(
        model=model,
        tools=ToolRegistry(),
        output_schemas={"FinalOutput": FinalOutput},
        settings=runtime_settings(),
    )

    result = await runtime.run(
        spec=agent_spec(allowed_tools=[], max_cost="1"),
        context=context(),
        permission=ToolPermission.READ,
    )

    assert result.status == "limit_reached"
    assert result.limit_reached is not None
    assert result.limit_reached.reason == "cost"
