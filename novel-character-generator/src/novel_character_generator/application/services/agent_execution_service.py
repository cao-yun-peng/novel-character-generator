import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.agents.structured_runtime import AgentRuntimeError
from novel_character_generator.application.ports.agent_runtime import (
    AgentContextPacket,
    AgentRunResult,
    AgentRuntime,
    AgentSpec,
    ToolPermission,
    ToolSpec,
)
from novel_character_generator.application.services.approval_service import (
    ApprovalService,
    CreatedApproval,
)
from novel_character_generator.infrastructure.db.orm import (
    AgentRunORM,
    AgentTurnORM,
    PipelineStepORM,
    ToolCallORM,
)


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class AgentExecution:
    agent_run_id: UUID
    result: AgentRunResult
    created_approval: CreatedApproval | None


class AgentExecutionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute(
        self,
        *,
        pipeline_step_id: UUID,
        expected_generation: int,
        runtime: AgentRuntime,
        spec: AgentSpec,
        context: AgentContextPacket,
        permission: ToolPermission,
        tool_specs: dict[str, ToolSpec],
        evaluation_version: str | None = None,
    ) -> AgentExecution:
        step = await self.session.get(PipelineStepORM, pipeline_step_id)
        if step is None:
            raise ValueError("pipeline_step_not_found")
        if step.status != "running" or step.lease_generation != expected_generation:
            raise ValueError("agent_step_not_running_or_lease_lost")
        missing_specs = set(spec.allowed_tools) - set(tool_specs)
        if missing_specs:
            raise ValueError("agent_tool_spec_missing")
        attempt = (
            await self.session.scalar(
                select(func.max(AgentRunORM.attempt)).where(
                    AgentRunORM.pipeline_step_id == pipeline_step_id,
                    AgentRunORM.agent_id == spec.agent_id,
                )
            )
            or 0
        ) + 1
        now = datetime.now(UTC)
        agent_run = AgentRunORM(
            id=uuid4(),
            pipeline_step_id=pipeline_step_id,
            agent_id=spec.agent_id,
            agent_version=spec.version,
            status="running",
            budget={
                "max_turns": spec.max_turns,
                "max_tool_calls": spec.max_tool_calls,
                "max_cost": str(spec.max_cost),
                "deadline_seconds": spec.deadline_seconds,
            },
            context_hash=context.context_hash,
            final_output_hash=None,
            stop_reason=None,
            attempt=attempt,
            agent_spec_snapshot=spec.model_dump(mode="json"),
            tool_spec_versions={name: tool_specs[name].version for name in spec.allowed_tools},
            prompt_version=spec.prompt_version,
            model_policy=spec.model_policy,
            output_schema=spec.output_schema,
            permission=permission.value,
            evaluation_version=evaluation_version,
            started_at=now,
            completed_at=None,
            input_tokens=0,
            output_tokens=0,
            total_cost=Decimal("0"),
            latency_ms=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(agent_run)
        await self.session.commit()

        started = perf_counter()
        try:
            result = await runtime.run(spec=spec, context=context, permission=permission)
        except AgentRuntimeError as error:
            await self._record_failure(agent_run.id, code=error.code, started=started)
            raise
        await self._record_result(
            agent_run_id=agent_run.id,
            result=result,
            tool_specs=tool_specs,
            started=started,
        )
        created_approval = None
        if result.approval_request is not None:
            created_approval = await ApprovalService(self.session).create_request(
                pipeline_step_id=pipeline_step_id,
                expected_generation=expected_generation,
                request=result.approval_request,
                requested_by_agent_run_id=agent_run.id,
            )
        else:
            await self.session.commit()
        return AgentExecution(
            agent_run_id=agent_run.id,
            result=result,
            created_approval=created_approval,
        )

    async def _record_result(
        self,
        *,
        agent_run_id: UUID,
        result: AgentRunResult,
        tool_specs: dict[str, ToolSpec],
        started: float,
    ) -> None:
        agent_run = await self.session.get_one(AgentRunORM, agent_run_id)
        now = datetime.now(UTC)
        for entry in result.history:
            self.session.add(
                AgentTurnORM(
                    id=uuid4(),
                    agent_run_id=agent_run_id,
                    turn_number=entry.turn_number,
                    input_context_hash=agent_run.context_hash,
                    output_summary={
                        "has_output": entry.output is not None,
                        "tool_call_count": len(entry.tool_calls),
                    },
                    usage=entry.usage.model_dump(mode="json"),
                    created_at=now,
                    updated_at=now,
                )
            )
            for call in entry.tool_calls:
                output = entry.tool_results.get(call.call_id)
                approval_call = (
                    result.approval_request is not None
                    and result.approval_request.tool_call.call_id == call.call_id
                )
                status = "succeeded" if output is not None else "not_executed"
                if approval_call:
                    status = "approval_required"
                tool_spec = tool_specs[call.tool_name]
                self.session.add(
                    ToolCallORM(
                        id=uuid4(),
                        agent_run_id=agent_run_id,
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        tool_version=tool_spec.version,
                        input_hash=_hash_json(call.arguments),
                        output_hash=_hash_json(output) if output is not None else None,
                        status=status,
                        side_effect=tool_spec.side_effect != "none",
                        duration_ms=entry.tool_durations_ms.get(call.call_id, 0),
                        error_code=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
        agent_run.status = {
            "completed": "succeeded",
            "approval_required": "waiting_approval",
            "limit_reached": "failed",
        }[result.status]
        agent_run.final_output_hash = (
            _hash_json(result.output) if result.output is not None else None
        )
        agent_run.stop_reason = result.stop_reason
        agent_run.completed_at = now
        agent_run.input_tokens = result.total_usage.input_tokens
        agent_run.output_tokens = result.total_usage.output_tokens
        agent_run.total_cost = result.total_usage.cost
        agent_run.latency_ms = round((perf_counter() - started) * 1_000)
        agent_run.updated_at = now
        await self.session.flush()

    async def _record_failure(self, agent_run_id: UUID, *, code: str, started: float) -> None:
        agent_run = await self.session.get_one(AgentRunORM, agent_run_id)
        now = datetime.now(UTC)
        agent_run.status = "failed"
        agent_run.stop_reason = code
        agent_run.completed_at = now
        agent_run.latency_ms = round((perf_counter() - started) * 1_000)
        agent_run.updated_at = now
        await self.session.commit()
