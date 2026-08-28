from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.entity_resolution import (
    ENTITY_CONVERGENCE_BATCH_SIZE,
    ENTITY_RESOLUTION_SCHEMA_VERSION,
    EntityConvergenceResult,
    EntityMemoryRecord,
    EntityResolutionProvider,
    EntityResolutionResult,
    GroundedCandidatePacket,
)
from novel_character_generator.application.ports.extraction import (
    DetailedExtractionProvider,
    ExtractionProvider,
    VisualCandidateExtractionResult,
)
from novel_character_generator.application.services.entity_resolution_service import (
    ENTITY_CONVERGENCE_REPAIR_POLICY,
    analyze_convergence_provider_result,
    apply_resolution_result,
    build_convergence_input,
    build_convergence_subset_input,
    build_resolution_input,
    conservatively_complete_convergence_result,
    downgrade_unverifiable_resolution_evidence,
    enforce_explicit_name_convergence_gate,
    enforce_explicit_name_link_gate,
    plan_convergence_shards,
    select_convergence_memory_frontier,
    select_resolution_memory,
    validate_convergence_result,
    validate_resolution_result,
)
from novel_character_generator.application.services.visual_candidate_adapter import (
    ground_visual_candidates,
)
from novel_character_generator.infrastructure.db.orm import (
    PipelineRunORM,
    PipelineStepORM,
    RunEventORM,
    SourceDocumentVersionORM,
    TimelineORM,
)
from novel_character_generator.infrastructure.db.repositories.entity_resolution import (
    EntityResolutionRepository,
    json_payload_hash,
    stable_json_hash,
)
from novel_character_generator.infrastructure.db.repositories.extraction import ExtractionRepository
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event
from novel_character_generator.infrastructure.llm.mock import MockEntityResolutionProvider
from novel_character_generator.workers.task_claim import (
    checkpoint_step,
    complete_step_and_enqueue,
    mark_cancelled,
    record_step_error,
    start_step,
)


async def process_extraction_run(
    session: AsyncSession,
    provider: ExtractionProvider,
    run_id: UUID,
    *,
    entity_provider: EntityResolutionProvider | None = None,
    entity_context_budget_tokens: int = 12_000,
    entity_memory_max_records: int = 64,
    entity_memory_recent_records: int = 16,
    entity_convergence_shard_max_records: int = 16,
    entity_convergence_shard_max_mentions: int = 32,
    entity_convergence_shard_max_input_tokens: int = 12_000,
    entity_convergence_shard_max_output_tokens: int = 4_500,
    entity_convergence_repair_max_attempts: int = 2,
    entity_max_calls: int = 2_000,
    capture_raw_responses: bool = False,
    max_attempts: int = 3,
    lease_seconds: int = 120,
) -> None:
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type not in {"character_extraction", "text_analysis"}:
        raise ValueError("extraction_run_not_found")
    step = await session.scalar(
        select(PipelineStepORM).where(
            PipelineStepORM.run_id == run_id,
            PipelineStepORM.step_key == "extract_characters",
        )
    )
    if step is None:
        raise RuntimeError("extraction_step_not_found")
    if step.status == "succeeded":
        return
    if step.status not in {"queued", "retry_scheduled", "claimed"}:
        raise ValueError("extraction_step_not_runnable")
    if run.cancel_requested:
        await mark_cancelled(
            session,
            step=step,
            run=run,
            expected_generation=step.lease_generation,
        )
        return
    step_id = step.id
    persisted_run_id = run.id
    expected_generation = await start_step(session, step=step, run=run)
    try:
        repository = ExtractionRepository(session)
        entity_repository = EntityResolutionRepository(session)
        resolver = entity_provider or MockEntityResolutionProvider()
        document = await repository.source_document(run.novel_id)
        normalization_map = await repository.normalization_map(document.id)
        timeline = await repository.canonical_timeline(run.novel_id)
        chunks = await repository.chunks(run.novel_id)
        cursor = step.cursor or {}
        start_ordinal = int(cursor.get("current_chunk_ordinal", 0))
        resolved_rows = await entity_repository.resolved_chunks(run.id)
        completed_batches = await entity_repository.completed_batches(run.id)
        memory = await entity_repository.stable_memory(run.novel_id)
        if resolved_rows and resolved_rows[-1].memory_after is not None:
            memory = [
                EntityMemoryRecord.model_validate(item) for item in resolved_rows[-1].memory_after
            ]
        if (
            completed_batches
            and completed_batches[-1].memory_after is not None
            and (
                not resolved_rows
                or completed_batches[-1].end_chunk_ordinal >= resolved_rows[-1].chunk_ordinal
            )
        ):
            memory = [
                EntityMemoryRecord.model_validate(item)
                for item in completed_batches[-1].memory_after
            ]
        convergence_call_count = int(
            await session.scalar(
                select(func.count())
                .select_from(RunEventORM)
                .where(
                    RunEventORM.run_id == run.id,
                    RunEventORM.event_type == "provider.entity_convergence.completed",
                )
            )
            or 0
        )
        call_count = sum(
            bool(GroundedCandidatePacket.model_validate(row.candidate_packet).mentions)
            for row in resolved_rows
        ) + convergence_call_count
        await session.commit()

        for chunk in chunks:
            if chunk.ordinal < start_ordinal:
                continue
            await session.refresh(run, attribute_names=["cancel_requested"])
            if run.cancel_requested:
                await mark_cancelled(
                    session,
                    step=step,
                    run=run,
                    expected_generation=expected_generation,
                )
                return
            record = await entity_repository.chunk_record(run.id, chunk.id)
            metadata = None
            raw_response: object | None = None
            raw_message_content: object | None = None
            if record is None:
                # Save extraction candidates before the second provider call. A retry
                # therefore does not pay for visual extraction twice.
                await session.commit()
                if isinstance(provider, DetailedExtractionProvider):
                    detailed = await provider.extract_chunk_detailed(chunk.content)
                    candidates = detailed.output
                    metadata = detailed.metadata
                    if capture_raw_responses:
                        raw_response = detailed.raw_response
                        raw_message_content = detailed.raw_message_content
                else:
                    candidates = await provider.extract_chunk(chunk.content)
                packet = ground_visual_candidates(
                    chunk.content,
                    candidates,
                    mention_id_prefix=f"{run.id}:{chunk.id}",
                )
                record = await entity_repository.save_extracted_candidates(
                    run=run,
                    chunk=chunk,
                    document=document,
                    normalization_map=normalization_map,
                    extraction_result=candidates.model_dump(mode="json"),
                    packet=packet,
                    provider_raw_response=raw_response,
                    provider_raw_message_content=raw_message_content,
                )
                await session.commit()
            else:
                candidates = VisualCandidateExtractionResult.model_validate(
                    record.extraction_result
                )
                packet = GroundedCandidatePacket.model_validate(record.candidate_packet)

            result_hash = sha256(
                candidates.model_dump_json(exclude_none=True).encode("utf-8")
            ).hexdigest()
            if metadata is not None:
                await append_run_event(
                    session,
                    run_id=run.id,
                    event_type="provider.extraction.completed",
                    payload={
                        "step_id": str(step.id),
                        "chunk_id": str(chunk.id),
                        "chunk_ordinal": chunk.ordinal,
                        "extractor_version": provider.version,
                        "input_hash": sha256(chunk.content.encode("utf-8")).hexdigest(),
                        "result_hash": result_hash,
                        **metadata.model_dump(mode="json"),
                    },
                )
            if record.status == "resolved" and record.memory_after is not None:
                memory = [EntityMemoryRecord.model_validate(item) for item in record.memory_after]
            else:
                previous_tail = chunks[chunk.ordinal - 1].content[-4_000:] if chunk.ordinal else ""
                memory_selection = select_resolution_memory(
                    packet=packet,
                    memory=memory,
                    chunk_ordinal=chunk.ordinal,
                    max_records=entity_memory_max_records,
                    recent_records=entity_memory_recent_records,
                )
                resolution_request = build_resolution_input(
                    chunk_id=chunk.id,
                    chunk_ordinal=chunk.ordinal,
                    chunk_text=chunk.content,
                    previous_chunk_tail=previous_tail,
                    packet=packet,
                    memory=list(memory_selection.records),
                    max_context_tokens=entity_context_budget_tokens,
                )
                if packet.mentions:
                    if call_count >= entity_max_calls:
                        raise RuntimeError("entity_resolution_call_budget_exceeded")
                    await session.commit()
                    resolution_result = await resolver.resolve_chunk(resolution_request)
                    if capture_raw_responses:
                        record.resolver_raw_response = getattr(
                            resolver, "last_raw_response", None
                        )
                        record.resolver_raw_message_content = getattr(
                            resolver, "last_raw_message_content", None
                        )
                        record.resolver_raw_response_hash = json_payload_hash(
                            record.resolver_raw_response
                        )
                    resolution_result = downgrade_unverifiable_resolution_evidence(
                        resolution_request,
                        resolution_result,
                    )
                    resolution_result = enforce_explicit_name_link_gate(
                        resolution_request,
                        resolution_result,
                    )
                    call_count += 1
                else:
                    resolution_result = EntityResolutionResult()
                validate_resolution_result(resolution_request, resolution_result)
                memory = apply_resolution_result(
                    resolution_request,
                    resolution_result,
                    base_memory=memory,
                )
                if packet.mentions:
                    await append_run_event(
                        session,
                        run_id=run.id,
                        event_type="provider.entity_resolution.completed",
                        payload={
                            "step_id": str(step.id),
                            "chunk_id": str(chunk.id),
                            "chunk_ordinal": chunk.ordinal,
                            "resolver_version": resolver.version,
                            "input_hash": stable_json_hash(resolution_request),
                            "result_hash": stable_json_hash(resolution_result),
                            "context_truncated": resolution_request.text_truncated,
                            "memory_selection": memory_selection.trace_payload(
                                updated_memory=memory
                            ),
                            "call_number": call_count,
                            **(getattr(resolver, "last_call_metadata", None) or {}),
                        },
                    )
                record.resolution_input_hash = stable_json_hash(resolution_request)
                record.resolution_result = resolution_result.model_dump(mode="json")
                record.memory_after = [item.model_dump(mode="json") for item in memory]
                record.resolver_version = resolver.version
                record.context_truncated = resolution_request.text_truncated
                record.status = "resolved"
                await session.flush()

            if (chunk.ordinal + 1) % ENTITY_CONVERGENCE_BATCH_SIZE == 0:
                memory, call_count = await _converge(
                    session=session,
                    repository=entity_repository,
                    extraction_repository=repository,
                    resolver=resolver,
                    run=run,
                    document=document,
                    timeline=timeline,
                    memory=memory,
                    batch_index=chunk.ordinal // ENTITY_CONVERGENCE_BATCH_SIZE,
                    start=chunk.ordinal - ENTITY_CONVERGENCE_BATCH_SIZE + 1,
                    end=chunk.ordinal,
                    final_batch=chunk.ordinal == len(chunks) - 1,
                    extractor_version=provider.version,
                    call_count=call_count,
                    max_calls=entity_max_calls,
                    shard_max_records=entity_convergence_shard_max_records,
                    shard_max_mentions=entity_convergence_shard_max_mentions,
                    shard_max_input_tokens=entity_convergence_shard_max_input_tokens,
                    shard_max_output_tokens=entity_convergence_shard_max_output_tokens,
                    repair_max_attempts=entity_convergence_repair_max_attempts,
                    capture_raw_responses=capture_raw_responses,
                )
            await checkpoint_step(
                session,
                step=step,
                expected_generation=expected_generation,
                cursor={
                    "schema_version": "v3",
                    "entity_resolution_schema": ENTITY_RESOLUTION_SCHEMA_VERSION,
                    "stage": "chunk_resolved",
                    "current_chunk_ordinal": chunk.ordinal + 1,
                    "completed_artifact_hash": result_hash,
                    "completed_step_keys": [],
                },
                lease_seconds=lease_seconds,
            )
        if chunks and len(chunks) % ENTITY_CONVERGENCE_BATCH_SIZE:
            batch_index = (len(chunks) - 1) // ENTITY_CONVERGENCE_BATCH_SIZE
            start = batch_index * ENTITY_CONVERGENCE_BATCH_SIZE
            memory, call_count = await _converge(
                session=session,
                repository=entity_repository,
                extraction_repository=repository,
                resolver=resolver,
                run=run,
                document=document,
                timeline=timeline,
                memory=memory,
                batch_index=batch_index,
                start=start,
                end=len(chunks) - 1,
                final_batch=True,
                extractor_version=provider.version,
                call_count=call_count,
                max_calls=entity_max_calls,
                shard_max_records=entity_convergence_shard_max_records,
                shard_max_mentions=entity_convergence_shard_max_mentions,
                shard_max_input_tokens=entity_convergence_shard_max_input_tokens,
                shard_max_output_tokens=entity_convergence_shard_max_output_tokens,
                repair_max_attempts=entity_convergence_repair_max_attempts,
                capture_raw_responses=capture_raw_responses,
            )
        await complete_step_and_enqueue(
            session,
            step=step,
            run=run,
            expected_generation=expected_generation,
            cursor={
                "schema_version": "v3",
                "entity_resolution_schema": ENTITY_RESOLUTION_SCHEMA_VERSION,
                "stage": "completed",
                "current_chunk_ordinal": len(chunks),
                "extractor_version": f"{provider.version}|{resolver.version}",
                "completed_step_keys": [step.step_key],
            },
            next_step_key="resolve_character_phases",
        )
    except Exception as error:
        provider_error_code = getattr(error, "code", None)
        provider_retryable = bool(getattr(error, "retryable", False))
        await record_step_error(
            session,
            step_id=step_id,
            run_id=persisted_run_id,
            error_code="extraction_failed",
            error=error,
            # A governed provider has already consumed its bounded in-call retry
            # budget. Do not schedule another automatic task attempt and charge
            # for the same chunk again; a user may explicitly retry the run later.
            max_attempts=1 if provider_error_code is not None else max_attempts,
            expected_generation=expected_generation,
        )
        await append_run_event(
            session,
            run_id=persisted_run_id,
            event_type=(
                "provider.extraction.deferred"
                if provider_error_code is not None and provider_retryable
                else "provider.extraction.failed"
            ),
            payload={
                "step_id": str(step_id),
                "error_code": str(provider_error_code or "extraction_failed"),
                "retryable": provider_retryable,
                "provider_attempts": int(getattr(error, "attempts", 1)),
            },
        )
        await session.commit()
        raise


async def _converge(
    *,
    session: AsyncSession,
    repository: EntityResolutionRepository,
    extraction_repository: ExtractionRepository,
    resolver: EntityResolutionProvider,
    run: PipelineRunORM,
    document: SourceDocumentVersionORM,
    timeline: TimelineORM,
    memory: list[EntityMemoryRecord],
    batch_index: int,
    start: int,
    end: int,
    final_batch: bool,
    extractor_version: str,
    call_count: int,
    max_calls: int,
    shard_max_records: int,
    shard_max_mentions: int,
    shard_max_input_tokens: int,
    shard_max_output_tokens: int,
    repair_max_attempts: int,
    capture_raw_responses: bool,
) -> tuple[list[EntityMemoryRecord], int]:
    existing = await repository.convergence_batch(run.id, batch_index)
    if existing is not None and existing.status in {"completed", "completed_with_warnings"}:
        assert existing.memory_after is not None
        return (
            [EntityMemoryRecord.model_validate(item) for item in existing.memory_after],
            call_count,
        )
    rows = await repository.resolved_chunks(run.id, start=start, end=end)
    packets = [GroundedCandidatePacket.model_validate(row.candidate_packet) for row in rows]
    frontier = select_convergence_memory_frontier(memory=memory, packets=packets)
    request = build_convergence_input(
        batch_index=batch_index,
        start_chunk_ordinal=start,
        end_chunk_ordinal=end,
        final_batch=final_batch,
        memory=memory,
        provisional_memory=list(frontier.records),
        chapter_decisions=[
            {
                "chunk_ordinal": row.chunk_ordinal,
                "result": row.resolution_result or {"decisions": []},
            }
            for row in rows
        ],
        packets=packets,
    )
    input_hash = stable_json_hash(request)
    batch = await repository.create_convergence_batch(
        run_id=run.id,
        batch_index=batch_index,
        start=start,
        end=end,
        final_batch=final_batch,
        input_hash=input_hash,
        resolver_version=resolver.version,
    )
    await session.commit()
    sharding = plan_convergence_shards(
        request,
        max_records=shard_max_records,
        max_mentions=shard_max_mentions,
        max_input_tokens=shard_max_input_tokens,
        max_output_tokens=shard_max_output_tokens,
        input_token_overhead=int(
            getattr(resolver, "convergence_input_token_overhead", 1_024)
        ),
    )
    initial_provider_decisions = []
    final_decisions = []
    raw_responses: list[object] = []
    raw_messages: list[object] = []
    shard_execution: list[dict[str, object]] = []
    total_repair_attempts = 0
    total_initial_uncovered = 0
    total_repaired_mentions = 0
    total_fallback_mentions = 0
    any_repair_call_budget_exhausted = False

    for shard in sharding.shards:
        if call_count >= max_calls:
            raise RuntimeError("entity_resolution_call_budget_exceeded")
        await session.commit()
        provider_result = await resolver.converge_batch(shard.request)
        provider_metadata = dict(getattr(resolver, "last_call_metadata", None) or {})
        if capture_raw_responses:
            raw_responses.append(
                {
                    "shard_index": shard.index,
                    "call_kind": "initial",
                    "repair_attempt": 0,
                    "response": getattr(resolver, "last_raw_response", None),
                }
            )
            raw_messages.append(
                {
                    "shard_index": shard.index,
                    "call_kind": "initial",
                    "repair_attempt": 0,
                    "content": getattr(resolver, "last_raw_message_content", None),
                }
            )
        call_count += 1
        initial_provider_decisions.extend(provider_result.decisions)
        coverage = analyze_convergence_provider_result(shard.request, provider_result)
        await append_run_event(
            session,
            run_id=run.id,
            event_type="provider.entity_convergence.completed",
            payload={
                "batch_index": batch_index,
                "start_chunk_ordinal": start,
                "end_chunk_ordinal": end,
                "final_batch": final_batch,
                "resolver_version": resolver.version,
                "batch_input_hash": input_hash,
                "input_hash": stable_json_hash(shard.request),
                "provider_result_hash": stable_json_hash(provider_result),
                "result_hash": stable_json_hash(coverage.accepted_result),
                "call_number": call_count,
                "call_kind": "initial",
                "repair_attempt": 0,
                "shard_index": shard.index,
                "shard_count": len(sharding.shards),
                **shard.trace_payload(),
                **coverage.trace_payload(),
                **provider_metadata,
            },
        )

        accepted_decisions = list(coverage.accepted_result.decisions)
        missing_record_ids = set(coverage.missing_record_ids)
        initial_uncovered = coverage.uncovered_mentions
        total_initial_uncovered += initial_uncovered
        repair_attempt = 0
        repaired_mentions = 0
        repair_call_budget_exhausted = False
        while missing_record_ids and repair_attempt < repair_max_attempts:
            if call_count >= max_calls:
                repair_call_budget_exhausted = True
                any_repair_call_budget_exhausted = True
                break
            repair_attempt += 1
            repair_records = [
                item
                for item in shard.request.provisional_memory
                if item.memory_id in missing_record_ids
            ]
            repair_request = build_convergence_subset_input(shard.request, repair_records)
            await session.commit()
            repair_result = await resolver.converge_batch(repair_request)
            repair_metadata = dict(getattr(resolver, "last_call_metadata", None) or {})
            if capture_raw_responses:
                raw_responses.append(
                    {
                        "shard_index": shard.index,
                        "call_kind": "repair",
                        "repair_attempt": repair_attempt,
                        "response": getattr(resolver, "last_raw_response", None),
                    }
                )
                raw_messages.append(
                    {
                        "shard_index": shard.index,
                        "call_kind": "repair",
                        "repair_attempt": repair_attempt,
                        "content": getattr(resolver, "last_raw_message_content", None),
                    }
                )
            call_count += 1
            repair_coverage = analyze_convergence_provider_result(
                repair_request, repair_result
            )
            accepted_decisions.extend(repair_coverage.accepted_result.decisions)
            previous_uncovered = sum(
                len(item.mention_ids)
                for item in repair_request.provisional_memory
            )
            missing_record_ids = set(repair_coverage.missing_record_ids)
            remaining_uncovered = sum(
                len(item.mention_ids)
                for item in repair_request.provisional_memory
                if item.memory_id in missing_record_ids
            )
            repaired_mentions += previous_uncovered - remaining_uncovered
            total_repair_attempts += 1
            await append_run_event(
                session,
                run_id=run.id,
                event_type="provider.entity_convergence.completed",
                payload={
                    "batch_index": batch_index,
                    "start_chunk_ordinal": start,
                    "end_chunk_ordinal": end,
                    "final_batch": final_batch,
                    "resolver_version": resolver.version,
                    "batch_input_hash": input_hash,
                    "input_hash": stable_json_hash(repair_request),
                    "provider_result_hash": stable_json_hash(repair_result),
                    "result_hash": stable_json_hash(repair_coverage.accepted_result),
                    "call_number": call_count,
                    "call_kind": "repair",
                    "repair_attempt": repair_attempt,
                    "shard_index": shard.index,
                    "shard_count": len(sharding.shards),
                    "records": len(repair_request.provisional_memory),
                    "mentions": previous_uncovered,
                    **repair_coverage.trace_payload(),
                    **repair_metadata,
                },
            )

        safe_provider_result = EntityConvergenceResult(decisions=accepted_decisions)
        shard_result = conservatively_complete_convergence_result(
            shard.request, safe_provider_result
        )
        shard_result = enforce_explicit_name_convergence_gate(
            shard.request, shard_result
        )
        validate_convergence_result(shard.request, shard_result)
        final_decisions.extend(shard_result.decisions)
        fallback_mentions = sum(
            len(item.mention_ids)
            for item in shard.request.provisional_memory
            if item.memory_id in missing_record_ids
        )
        total_repaired_mentions += repaired_mentions
        total_fallback_mentions += fallback_mentions
        shard_execution.append(
            {
                **shard.trace_payload(),
                "initial_uncovered_mentions": initial_uncovered,
                "repair_attempts": repair_attempt,
                "repaired_mentions": repaired_mentions,
                "fallback_mentions": fallback_mentions,
                "repair_call_budget_exhausted": repair_call_budget_exhausted,
                "final_provider_coverage_ratio": (
                    (shard.mention_count - fallback_mentions) / shard.mention_count
                    if shard.mention_count
                    else 1.0
                ),
            }
        )

    result = EntityConvergenceResult(decisions=final_decisions)
    provider_result = EntityConvergenceResult(decisions=initial_provider_decisions)
    if capture_raw_responses:
        batch.resolver_raw_response = raw_responses
        batch.resolver_raw_message_content = raw_messages
        batch.resolver_raw_response_hash = json_payload_hash(raw_responses)
    validate_convergence_result(request, result)
    memory, _ = await repository.materialize_convergence(
        run=run,
        document=document,
        timeline=timeline,
        result=result,
        memory=memory,
        extractor_version=extractor_version,
        resolver_version=resolver.version,
    )
    await append_run_event(
        session,
        run_id=run.id,
        event_type="entity.convergence.frontier.completed",
        payload={
            "batch_index": batch_index,
            "start_chunk_ordinal": start,
            "end_chunk_ordinal": end,
            "final_batch": final_batch,
            "resolver_version": resolver.version,
            "input_hash": input_hash,
            "convergence_frontier": frontier.trace_payload(
                stable_context_records=len(request.stable_memory),
                provider_result=provider_result,
                completed_result=result,
                updated_memory=memory,
            ),
            "convergence_sharding": {
                **sharding.trace_payload(),
                "repair_policy": ENTITY_CONVERGENCE_REPAIR_POLICY,
                "repair_max_attempts": repair_max_attempts,
                "provider_calls": len(sharding.shards) + total_repair_attempts,
                "repair_attempts": total_repair_attempts,
                "initial_uncovered_mentions": total_initial_uncovered,
                "repaired_mentions": total_repaired_mentions,
                "fallback_mentions": total_fallback_mentions,
                "repair_call_budget_exhausted": any_repair_call_budget_exhausted,
                "final_provider_coverage_ratio": (
                    (len({
                        mention_id
                        for item in request.provisional_memory
                        for mention_id in item.mention_ids
                    }) - total_fallback_mentions)
                    / len({
                        mention_id
                        for item in request.provisional_memory
                        for mention_id in item.mention_ids
                    })
                    if request.provisional_memory
                    else 1.0
                ),
                "shards": shard_execution,
            },
        },
    )
    batch.result = result.model_dump(mode="json")
    batch.memory_after = [item.model_dump(mode="json") for item in memory]
    batch.resolver_version = resolver.version
    batch.status = (
        "completed_with_warnings" if total_fallback_mentions else "completed"
    )
    await session.flush()
    return memory, call_count
