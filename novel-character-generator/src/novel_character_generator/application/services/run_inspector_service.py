import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.infrastructure.db.orm import (
    CharacterConvergenceBatchORM,
    CharacterLifePhaseORM,
    CharacterPhaseResolutionORM,
    CharacterResolutionChunkORM,
    FeatureObservationORM,
    ObservationScopeBindingORM,
    PipelineRunORM,
    PipelineStepORM,
    RunEventORM,
    SourceDocumentORM,
    TemporalSignalORM,
    TextChunkORM,
)

InspectorStageKey = Literal["r1", "r2", "r3"]
InspectorOutputKind = Literal["r1_chunk", "r2_chunk", "r2_convergence", "r3_character"]


class InspectorOutputRef(BaseModel):
    id: UUID
    kind: InspectorOutputKind
    label: str
    status: str
    ordinal: int | None = None
    version: str | None = None


class InspectorUsage(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    cache_hit_tokens: int = 0
    reasoning_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0


class InspectorStage(BaseModel):
    key: InspectorStageKey
    title: str
    execution_kind: Literal["model", "hybrid", "code"]
    status: str
    progress_current: int = 0
    progress_total: int = 0
    usage: InspectorUsage = Field(default_factory=InspectorUsage)
    metrics: dict[str, int | float | str | None] = Field(default_factory=dict)
    attention_reasons: list[str] = Field(default_factory=list)
    quality_note: str
    outputs: list[InspectorOutputRef] = Field(default_factory=list)


class RunInspectorSummary(BaseModel):
    schema_version: Literal["run-inspector-v1"] = "run-inspector-v1"
    run_id: UUID
    run_status: str
    stages: list[InspectorStage]


class InspectorOutputDetail(BaseModel):
    schema_version: Literal["run-inspector-output-v1"] = "run-inspector-output-v1"
    run_id: UUID
    id: UUID
    kind: InspectorOutputKind
    label: str
    status: str
    input_hash: str | None = None
    version: str | None = None
    output: dict[str, Any]
    intermediate: dict[str, Any] | list[dict[str, Any]] | None = None
    trace: dict[str, Any] | None = None


class RawModelResponseDetail(BaseModel):
    schema_version: Literal["raw-model-response-v1"] = "raw-model-response-v1"
    run_id: UUID
    output_id: UUID
    kind: Literal["r1_chunk", "r2_chunk", "r2_convergence"]
    ordinal: int
    captured_at: datetime
    payload_hash: str
    message_content: Any
    response_payload: Any


def _list_size(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _float_value(value: object) -> float:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    return 0


def _stage_status(
    *, current: int, total: int, step: PipelineStepORM | None, complete_when_empty: bool = False
) -> str:
    if total > 0 and current >= total:
        return "succeeded"
    if complete_when_empty and total == 0 and step is not None and step.status == "succeeded":
        return "succeeded"
    if current > 0:
        return "running"
    if step is None:
        return "pending"
    if step.status in {"claimed", "running", "retry_scheduled"}:
        return "running"
    return step.status


def _usage(events: list[RunEventORM], event_types: set[str]) -> InspectorUsage:
    usage = InspectorUsage()
    for event in events:
        if event.event_type not in event_types:
            continue
        usage.calls += 1
        raw_usage = event.payload.get("usage")
        if isinstance(raw_usage, dict):
            usage.input_tokens += _int_value(
                raw_usage.get("input_tokens", raw_usage.get("prompt_tokens"))
            )
            usage.cache_hit_tokens += _int_value(raw_usage.get("cache_hit_tokens"))
            usage.reasoning_tokens += _int_value(raw_usage.get("reasoning_tokens"))
            usage.output_tokens += _int_value(
                raw_usage.get("output_tokens", raw_usage.get("completion_tokens"))
            )
            usage.total_tokens += _int_value(raw_usage.get("total_tokens"))
        usage.latency_ms += _float_value(event.payload.get("latency_ms"))
    return usage


def _event_failures(events: list[RunEventORM], prefix: str) -> int:
    return sum(
        event.event_type.startswith(prefix)
        and (event.event_type.endswith(".failed") or event.event_type.endswith(".deferred"))
        for event in events
    )


def _memory_status_counts(memory: list[dict[str, Any]] | None) -> Counter[str]:
    statuses: Counter[str] = Counter()
    for item in memory or []:
        value = item.get("status")
        if isinstance(value, str):
            statuses[value] += 1
    return statuses


class RunInspectorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self, run_id: UUID) -> RunInspectorSummary | None:
        run = await self.session.get(PipelineRunORM, run_id)
        if run is None:
            return None

        steps = list(
            await self.session.scalars(
                select(PipelineStepORM).where(PipelineStepORM.run_id == run_id)
            )
        )
        step_by_key = {step.step_key: step for step in steps}
        extraction_step = step_by_key.get("extract_characters")
        phase_step = step_by_key.get("resolve_character_phases")

        chunks = list(
            await self.session.scalars(
                select(CharacterResolutionChunkORM)
                .where(CharacterResolutionChunkORM.run_id == run_id)
                .order_by(CharacterResolutionChunkORM.chunk_ordinal)
            )
        )
        batches = list(
            await self.session.scalars(
                select(CharacterConvergenceBatchORM)
                .where(CharacterConvergenceBatchORM.run_id == run_id)
                .order_by(CharacterConvergenceBatchORM.batch_index)
            )
        )
        phase_resolutions = list(
            await self.session.scalars(
                select(CharacterPhaseResolutionORM)
                .where(CharacterPhaseResolutionORM.run_id == run_id)
                .order_by(CharacterPhaseResolutionORM.created_at)
            )
        )
        events = list(
            await self.session.scalars(
                select(RunEventORM)
                .where(RunEventORM.run_id == run_id)
                .order_by(RunEventORM.sequence)
            )
        )
        total_chunks = await self._current_chunk_count(run.novel_id)

        visual_candidates = sum(
            _list_size(row.extraction_result.get("visual_candidates")) for row in chunks
        )
        entity_mentions = sum(_list_size(row.candidate_packet.get("mentions")) for row in chunks)
        grounded_facts = sum(_list_size(row.candidate_packet.get("facts")) for row in chunks)
        temporal_candidates = sum(
            _list_size(row.candidate_packet.get("temporal_signals")) for row in chunks
        )
        deferred_items = sum(
            _list_size(row.extraction_result.get("deferred_items")) for row in chunks
        )
        warnings = sum(_list_size(row.candidate_packet.get("warnings")) for row in chunks)
        r1_failures = _event_failures(events, "provider.extraction")
        r1_attention: list[str] = []
        if deferred_items:
            r1_attention.append("deferred_items_present")
        if warnings:
            r1_attention.append("grounding_warnings_present")
        if r1_failures:
            r1_attention.append("provider_failures_or_deferrals")
        r1 = InspectorStage(
            key="r1",
            title="R1 视觉候选与证据定位",
            execution_kind="hybrid",
            status=_stage_status(
                current=len(chunks), total=total_chunks, step=extraction_step
            ),
            progress_current=len(chunks),
            progress_total=total_chunks,
            usage=_usage(events, {"provider.extraction.completed"}),
            metrics={
                "visual_candidates": visual_candidates,
                "entity_mentions": entity_mentions,
                "grounded_facts": grounded_facts,
                "grounding_acceptance_rate": (
                    round(grounded_facts / visual_candidates * 100, 1)
                    if visual_candidates
                    else 0.0
                ),
                "temporal_signals": temporal_candidates,
                "deferred_items": deferred_items,
                "warnings": warnings,
                "provider_failures": r1_failures,
            },
            attention_reasons=r1_attention,
            quality_note=(
                "候选与定位计数是运行信号；未关联黄金集时不代表 precision/recall。"
            ),
            outputs=[
                InspectorOutputRef(
                    id=row.id,
                    kind="r1_chunk",
                    label=f"Chunk {row.chunk_ordinal} 候选与定位产出",
                    status="completed",
                    ordinal=row.chunk_ordinal,
                    version=next(
                        (
                            str(event.payload.get("extractor_version"))
                            for event in reversed(events)
                            if event.event_type == "provider.extraction.completed"
                            and event.payload.get("chunk_id") == str(row.source_chunk_id)
                            and event.payload.get("extractor_version")
                        ),
                        None,
                    ),
                )
                for row in chunks
            ],
        )

        resolved_chunks = [row for row in chunks if row.status == "resolved"]
        final_memory = (
            batches[-1].memory_after
            if batches and batches[-1].memory_after is not None
            else resolved_chunks[-1].memory_after
            if resolved_chunks
            else None
        )
        memory_counts = _memory_status_counts(final_memory)
        r2_failures = _event_failures(events, "provider.entity")
        r2_memory_selections = [
            selection
            for event in events
            if event.event_type == "provider.entity_resolution.completed"
            for selection in [event.payload.get("memory_selection")]
            if isinstance(selection, dict)
        ]
        r2_convergence_frontiers = [
            frontier
            for event in events
            if event.event_type == "entity.convergence.frontier.completed"
            for frontier in [event.payload.get("convergence_frontier")]
            if isinstance(frontier, dict)
        ]
        r2_convergence_sharding = [
            sharding
            for event in events
            if event.event_type == "entity.convergence.frontier.completed"
            for sharding in [event.payload.get("convergence_sharding")]
            if isinstance(sharding, dict)
        ]
        r2_attention: list[str] = []
        if memory_counts["provisional"]:
            r2_attention.append("provisional_entities_present")
        if memory_counts["unresolved"]:
            r2_attention.append("unresolved_entities_present")
        if r2_failures:
            r2_attention.append("provider_failures_or_deferrals")
        if any(bool(item.get("truncated")) for item in r2_memory_selections):
            r2_attention.append("entity_memory_context_truncated")
        if any(
            _int_value(item.get("provider_omitted_mentions")) > 0
            for item in r2_convergence_frontiers
        ):
            r2_attention.append("entity_convergence_provider_omissions")
        if any(
            _int_value(item.get("fallback_mentions")) > 0
            for item in r2_convergence_sharding
        ):
            r2_attention.append("entity_convergence_repair_exhausted")
        r2_outputs = [
            InspectorOutputRef(
                id=row.id,
                kind="r2_chunk",
                label=f"Chunk {row.chunk_ordinal} 人物解析",
                status=row.status,
                ordinal=row.chunk_ordinal,
                version=row.resolver_version,
            )
            for row in chunks
            if row.resolution_result is not None
        ]
        r2_outputs.extend(
            InspectorOutputRef(
                id=row.id,
                kind="r2_convergence",
                label=(
                    f"收敛批次 {row.batch_index}"
                    f"（{row.start_chunk_ordinal}-{row.end_chunk_ordinal}）"
                ),
                status=row.status,
                ordinal=row.batch_index,
                version=row.resolver_version,
            )
            for row in batches
        )
        r2 = InspectorStage(
            key="r2",
            title="R2 人物实体解析与收敛",
            execution_kind="model",
            status=_stage_status(
                current=len(resolved_chunks), total=len(chunks), step=extraction_step
            ),
            progress_current=len(resolved_chunks),
            progress_total=len(chunks),
            usage=_usage(
                events,
                {
                    "provider.entity_resolution.completed",
                    "provider.entity_convergence.completed",
                },
            ),
            metrics={
                "resolved_chunks": len(resolved_chunks),
                "convergence_batches": len(batches),
                "stable_entities": memory_counts["stable"],
                "provisional_entities": memory_counts["provisional"],
                "unresolved_entities": memory_counts["unresolved"],
                "provider_failures": r2_failures,
                "memory_selection_calls": len(r2_memory_selections),
                "max_memory_records_before": max(
                    (_int_value(item.get("records_before")) for item in r2_memory_selections),
                    default=0,
                ),
                "max_memory_records_selected": max(
                    (_int_value(item.get("records_selected")) for item in r2_memory_selections),
                    default=0,
                ),
                "memory_records_dropped_total": sum(
                    _int_value(item.get("records_dropped")) for item in r2_memory_selections
                ),
                "convergence_frontier_batches": len(r2_convergence_frontiers),
                "convergence_frontier_records_total": sum(
                    _int_value(item.get("frontier_records"))
                    for item in r2_convergence_frontiers
                ),
                "convergence_deferred_records_total": sum(
                    _int_value(item.get("deferred_records"))
                    for item in r2_convergence_frontiers
                ),
                "max_convergence_frontier_mentions": max(
                    (
                        _int_value(item.get("frontier_mentions"))
                        for item in r2_convergence_frontiers
                    ),
                    default=0,
                ),
                "convergence_provider_omitted_mentions": sum(
                    _int_value(item.get("provider_omitted_mentions"))
                    for item in r2_convergence_frontiers
                ),
                "convergence_shards_total": sum(
                    _int_value(item.get("shard_count"))
                    for item in r2_convergence_sharding
                ),
                "convergence_provider_calls_total": sum(
                    _int_value(item.get("provider_calls"))
                    for item in r2_convergence_sharding
                ),
                "convergence_repair_attempts_total": sum(
                    _int_value(item.get("repair_attempts"))
                    for item in r2_convergence_sharding
                ),
                "convergence_initial_uncovered_mentions": sum(
                    _int_value(item.get("initial_uncovered_mentions"))
                    for item in r2_convergence_sharding
                ),
                "convergence_repaired_mentions": sum(
                    _int_value(item.get("repaired_mentions"))
                    for item in r2_convergence_sharding
                ),
                "convergence_fallback_mentions": sum(
                    _int_value(item.get("fallback_mentions"))
                    for item in r2_convergence_sharding
                ),
                "max_convergence_shard_records": max(
                    (
                        _int_value(item.get("max_shard_records"))
                        for item in r2_convergence_sharding
                    ),
                    default=0,
                ),
                "max_convergence_shard_mentions": max(
                    (
                        _int_value(item.get("max_shard_mentions"))
                        for item in r2_convergence_sharding
                    ),
                    default=0,
                ),
                "max_convergence_shard_estimated_input_tokens": max(
                    (
                        _int_value(item.get("max_estimated_input_tokens"))
                        for item in r2_convergence_sharding
                    ),
                    default=0,
                ),
                "max_convergence_shard_estimated_output_tokens": max(
                    (
                        _int_value(item.get("max_estimated_output_tokens"))
                        for item in r2_convergence_sharding
                    ),
                    default=0,
                ),
            },
            attention_reasons=r2_attention,
            quality_note=(
                "stable/provisional/unresolved 是解析状态；人物归属正确性仍需 mention 黄金集。"
            ),
            outputs=r2_outputs,
        )

        phase_count = await self._count(CharacterLifePhaseORM, run_id)
        final_bindings = await self._count(
            ObservationScopeBindingORM, run_id, status="final"
        )
        review_bindings = await self._count(
            ObservationScopeBindingORM, run_id, status="needs_review"
        )
        unresolved_signals = await self._count(
            TemporalSignalORM, run_id, resolution_status="unresolved"
        )
        active_observations = await self._count(
            FeatureObservationORM, run_id, record_status="active", run_column="extraction_run_id"
        )
        pending_observations = await self._count(
            FeatureObservationORM, run_id, record_status="pending", run_column="extraction_run_id"
        )
        phase_cursor = phase_step.cursor if phase_step is not None else None
        phase_total = _int_value(phase_cursor.get("character_count")) if phase_cursor else 0
        phase_current = (
            _int_value(phase_cursor.get("current_character_index"))
            if phase_cursor
            else len(phase_resolutions)
        )
        r3_attention: list[str] = []
        if review_bindings:
            r3_attention.append("scope_review_required")
        if unresolved_signals:
            r3_attention.append("unresolved_temporal_signals")
        if pending_observations:
            r3_attention.append("pending_observations_present")
        r3 = InspectorStage(
            key="r3",
            title="R3 人生阶段与时间作用域",
            execution_kind="code",
            status=_stage_status(
                current=phase_current,
                total=phase_total,
                step=phase_step,
                complete_when_empty=True,
            ),
            progress_current=phase_current,
            progress_total=phase_total,
            metrics={
                "phase_resolutions": len(phase_resolutions),
                "life_phases": phase_count,
                "final_bindings": final_bindings,
                "needs_review_bindings": review_bindings,
                "unresolved_temporal_signals": unresolved_signals,
                "active_observations": active_observations,
                "pending_observations": pending_observations,
            },
            attention_reasons=r3_attention,
            quality_note=(
                "final/review 只表示策略门禁结果；phase/scope 正确性仍需阶段黄金集。"
            ),
            outputs=[
                InspectorOutputRef(
                    id=row.id,
                    kind="r3_character",
                    label=f"人物 {row.character_id} 阶段解析",
                    status=row.status,
                    version=row.resolver_version,
                )
                for row in phase_resolutions
            ],
        )
        return RunInspectorSummary(run_id=run.id, run_status=run.status, stages=[r1, r2, r3])

    async def output(
        self, run_id: UUID, kind: InspectorOutputKind, output_id: UUID
    ) -> InspectorOutputDetail | None:
        if await self.session.get(PipelineRunORM, run_id) is None:
            return None
        if kind == "r1_chunk":
            r1_row = await self.session.get(CharacterResolutionChunkORM, output_id)
            if r1_row is None or r1_row.run_id != run_id:
                return None
            source_chunk = await self.session.get(TextChunkORM, r1_row.source_chunk_id)
            input_hash = (
                hashlib.sha256(source_chunk.content.encode("utf-8")).hexdigest()
                if source_chunk is not None
                else None
            )
            event = next(
                (
                    item
                    for item in reversed(
                        list(
                            await self.session.scalars(
                                select(RunEventORM)
                                .where(
                                    RunEventORM.run_id == run_id,
                                    RunEventORM.event_type == "provider.extraction.completed",
                                )
                                .order_by(RunEventORM.sequence)
                            )
                        )
                    )
                    if item.payload.get("chunk_id") == str(r1_row.source_chunk_id)
                ),
                None,
            )
            trace: dict[str, Any] = {
                "input_hash": input_hash,
                "result_hash": hashlib.sha256(
                    json.dumps(
                        r1_row.extraction_result,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "status": "persisted",
            }
            if event is not None:
                trace_keys = (
                    "input_hash",
                    "result_hash",
                    "provider_request_id",
                    "response_model",
                    "wire_api",
                    "attempts",
                    "latency_ms",
                    "status",
                    "usage",
                )
                trace.update(
                    {key: event.payload[key] for key in trace_keys if key in event.payload}
                )
            return InspectorOutputDetail(
                run_id=run_id,
                id=r1_row.id,
                kind=kind,
                label=f"Chunk {r1_row.chunk_ordinal} 候选与定位产出",
                status="completed",
                input_hash=input_hash,
                version=(
                    str(event.payload.get("extractor_version")) if event is not None else None
                ),
                output=r1_row.extraction_result,
                intermediate=r1_row.candidate_packet,
                trace=trace,
            )
        if kind == "r2_chunk":
            r2_row = await self.session.get(CharacterResolutionChunkORM, output_id)
            if (
                r2_row is None
                or r2_row.run_id != run_id
                or r2_row.resolution_result is None
            ):
                return None
            r2_event = next(
                (
                    item
                    for item in reversed(
                        list(
                            await self.session.scalars(
                                select(RunEventORM)
                                .where(
                                    RunEventORM.run_id == run_id,
                                    RunEventORM.event_type
                                    == "provider.entity_resolution.completed",
                                )
                                .order_by(RunEventORM.sequence)
                            )
                        )
                    )
                    if item.payload.get("chunk_id") == str(r2_row.source_chunk_id)
                ),
                None,
            )
            r2_trace: dict[str, Any] | None = None
            if r2_event is not None:
                r2_trace_keys = (
                    "input_hash",
                    "result_hash",
                    "provider_request_id",
                    "response_model",
                    "wire_api",
                    "attempts",
                    "latency_ms",
                    "status",
                    "usage",
                    "context_truncated",
                    "memory_selection",
                )
                r2_trace = {
                    key: r2_event.payload[key]
                    for key in r2_trace_keys
                    if key in r2_event.payload
                }
            return InspectorOutputDetail(
                run_id=run_id,
                id=r2_row.id,
                kind=kind,
                label=f"Chunk {r2_row.chunk_ordinal} 人物解析",
                status=r2_row.status,
                input_hash=r2_row.resolution_input_hash,
                version=r2_row.resolver_version,
                output=r2_row.resolution_result,
                intermediate=r2_row.memory_after,
                trace=r2_trace,
            )
        if kind == "r2_convergence":
            batch_row = await self.session.get(CharacterConvergenceBatchORM, output_id)
            if batch_row is None or batch_row.run_id != run_id or batch_row.result is None:
                return None
            convergence_events = list(
                await self.session.scalars(
                    select(RunEventORM)
                    .where(
                        RunEventORM.run_id == run_id,
                        RunEventORM.event_type.in_(
                            (
                                "provider.entity_convergence.completed",
                                "entity.convergence.frontier.completed",
                            )
                        ),
                    )
                    .order_by(RunEventORM.sequence)
                )
            )
            provider_event = next(
                (
                    item
                    for item in reversed(convergence_events)
                    if item.event_type == "provider.entity_convergence.completed"
                    and item.payload.get("batch_index") == batch_row.batch_index
                ),
                None,
            )
            frontier_event = next(
                (
                    item
                    for item in reversed(convergence_events)
                    if item.event_type == "entity.convergence.frontier.completed"
                    and item.payload.get("batch_index") == batch_row.batch_index
                ),
                None,
            )
            convergence_trace: dict[str, Any] = {}
            if provider_event is not None:
                provider_trace_keys = (
                    "input_hash",
                    "provider_result_hash",
                    "result_hash",
                    "provider_request_id",
                    "response_model",
                    "wire_api",
                    "attempts",
                    "latency_ms",
                    "usage",
                    "call_kind",
                    "repair_attempt",
                    "shard_index",
                    "shard_count",
                    "expected_mentions",
                    "covered_mentions",
                    "omitted_mentions",
                    "uncovered_mentions",
                    "foreign_mentions",
                    "duplicate_mentions",
                    "unsafe_decisions",
                    "coverage_ratio",
                )
                convergence_trace.update(
                    {
                        key: provider_event.payload[key]
                        for key in provider_trace_keys
                        if key in provider_event.payload
                    }
                )
            if frontier_event is not None:
                convergence_trace["convergence_frontier"] = frontier_event.payload.get(
                    "convergence_frontier"
                )
                convergence_trace["convergence_sharding"] = frontier_event.payload.get(
                    "convergence_sharding"
                )
            return InspectorOutputDetail(
                run_id=run_id,
                id=batch_row.id,
                kind=kind,
                label=f"收敛批次 {batch_row.batch_index}",
                status=batch_row.status,
                input_hash=batch_row.input_hash,
                version=batch_row.resolver_version,
                output=batch_row.result,
                intermediate=batch_row.memory_after,
                trace=convergence_trace or None,
            )
        phase_row = await self.session.get(CharacterPhaseResolutionORM, output_id)
        if phase_row is None or phase_row.run_id != run_id:
            return None
        return InspectorOutputDetail(
            run_id=run_id,
            id=phase_row.id,
            kind=kind,
            label=f"人物 {phase_row.character_id} 阶段解析",
            status=phase_row.status,
            input_hash=phase_row.input_hash,
            version=phase_row.resolver_version,
            output=phase_row.result,
        )

    async def raw_model_response(
        self,
        run_id: UUID,
        kind: Literal["r1_chunk", "r2_chunk", "r2_convergence"],
        output_id: UUID,
    ) -> RawModelResponseDetail | None:
        if await self.session.get(PipelineRunORM, run_id) is None:
            return None
        if kind == "r2_convergence":
            batch = await self.session.get(CharacterConvergenceBatchORM, output_id)
            if (
                batch is None
                or batch.run_id != run_id
                or batch.resolver_raw_response is None
                or batch.resolver_raw_response_hash is None
            ):
                return None
            return RawModelResponseDetail(
                run_id=run_id,
                output_id=batch.id,
                kind=kind,
                ordinal=batch.batch_index,
                captured_at=batch.updated_at,
                payload_hash=batch.resolver_raw_response_hash,
                message_content=batch.resolver_raw_message_content,
                response_payload=batch.resolver_raw_response,
            )
        row = await self.session.get(CharacterResolutionChunkORM, output_id)
        response = (
            row.provider_raw_response
            if row is not None and kind == "r1_chunk"
            else row.resolver_raw_response if row is not None else None
        )
        message_content = (
            row.provider_raw_message_content
            if row is not None and kind == "r1_chunk"
            else row.resolver_raw_message_content if row is not None else None
        )
        payload_hash = (
            row.provider_raw_response_hash
            if row is not None and kind == "r1_chunk"
            else row.resolver_raw_response_hash if row is not None else None
        )
        if (
            row is None
            or row.run_id != run_id
            or response is None
            or payload_hash is None
        ):
            return None
        return RawModelResponseDetail(
            run_id=run_id,
            output_id=row.id,
            kind=kind,
            ordinal=row.chunk_ordinal,
            captured_at=row.updated_at,
            payload_hash=payload_hash,
            message_content=message_content,
            response_payload=response,
        )

    async def _current_chunk_count(self, novel_id: UUID) -> int:
        current_version_id = await self.session.scalar(
            select(SourceDocumentORM.current_version_id).where(
                SourceDocumentORM.novel_id == novel_id
            )
        )
        if current_version_id is None:
            return 0
        value = await self.session.scalar(
            select(func.count(TextChunkORM.id)).where(
                TextChunkORM.source_document_version_id == current_version_id
            )
        )
        return int(value or 0)

    async def _count(
        self,
        model: type[Any],
        run_id: UUID,
        *,
        run_column: str = "run_id",
        **filters: object,
    ) -> int:
        run_attribute = getattr(model, run_column)
        query = select(func.count(model.id)).where(run_attribute == run_id)
        for name, value in filters.items():
            query = query.where(getattr(model, name) == value)
        count = await self.session.scalar(query)
        return int(count or 0)
