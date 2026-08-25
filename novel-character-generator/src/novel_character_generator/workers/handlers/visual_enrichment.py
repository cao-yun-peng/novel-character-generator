from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.visual_enrichment import (
    VisualEnrichmentProvider,
    VisualEnrichmentResult,
)
from novel_character_generator.application.services.hybrid_retrieval_service import (
    HybridRetrievalService,
)
from novel_character_generator.application.services.visual_enrichment_service import (
    VisualEnrichmentService,
)
from novel_character_generator.infrastructure.db.orm import (
    ModelCallORM,
    PipelineRunORM,
    PipelineStepORM,
    RetrievalQueryRunORM,
)
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event
from novel_character_generator.infrastructure.llm.visual_enrichment import packet_hash
from novel_character_generator.workers.task_claim import (
    complete_step,
    complete_step_and_enqueue,
    mark_cancelled,
    record_step_error,
    start_step,
)

logger = logging.getLogger(__name__)


async def process_visual_enrichment_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    provider: VisualEnrichmentProvider | None = None,
    retrieval: HybridRetrievalService | None = None,
    bm25_top_k: int = 40,
    vector_top_k: int = 40,
    rrf_k: int = 60,
    main_hit_limit: int = 16,
    neighbor_count: int = 1,
    max_attempts: int = 3,
) -> None:
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type != "visual_enrichment":
        raise ValueError("visual_enrichment_run_not_found")
    step = await session.scalar(
        select(PipelineStepORM)
        .where(
            PipelineStepORM.run_id == run.id,
            PipelineStepORM.status.in_(("queued", "retry_scheduled", "claimed")),
        )
        .order_by(PipelineStepORM.created_at)
    )
    if step is None:
        raise ValueError("visual_enrichment_step_not_runnable")
    if run.cancel_requested:
        await mark_cancelled(
            session, step=step, run=run, expected_generation=step.lease_generation
        )
        return
    expected_generation = await start_step(session, step=step, run=run)
    step_id = step.id
    try:
        service = VisualEnrichmentService(session)
        cursor = step.cursor or {}
        request_hash = str(cursor.get("request_hash", ""))
        if step.step_key == "plan_visual_retrieval":
            planned_query = await service.plan(run, cursor)
            await complete_step_and_enqueue(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor={
                    **cursor,
                    "query_run_id": str(planned_query.id),
                    "query_plan_hash": planned_query.query_plan_hash,
                    "completed_step_keys": [step.step_key],
                },
                next_step_key="retrieve_visual_evidence",
                next_cursor={
                    "schema_version": "v1",
                    "request_hash": request_hash,
                    "query_run_id": str(planned_query.id),
                },
            )
            return
        query_run_id = UUID(str(cursor["query_run_id"]))
        query_record = await session.get(RetrievalQueryRunORM, query_run_id)
        if query_record is None or query_record.enrichment_run_id != run.id:
            raise RuntimeError("visual_enrichment_query_run_not_found")
        if step.step_key == "retrieve_visual_evidence":
            if retrieval is None:
                raise RuntimeError("visual_enrichment_retrieval_provider_required")
            packet = await service.retrieve(
                run=run,
                query_run=query_record,
                retrieval=retrieval,
                bm25_top_k=bm25_top_k,
                vector_top_k=vector_top_k,
                rrf_k=rrf_k,
                main_hit_limit=main_hit_limit,
                neighbor_count=neighbor_count,
            )
            fingerprint = packet_hash(packet)
            await append_run_event(
                session,
                run_id=run.id,
                event_type="visual_enrichment.packet_built",
                payload={
                    "query_run_id": str(query_record.id),
                    "packet_hash": fingerprint,
                    "passage_count": len(packet.passages),
                },
            )
            await complete_step_and_enqueue(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor={
                    **cursor,
                    "packet_hash": fingerprint,
                    "passage_count": len(packet.passages),
                    "completed_step_keys": [step.step_key],
                },
                next_step_key="extract_visual_evidence",
                next_cursor={
                    "schema_version": "v1",
                    "request_hash": request_hash,
                    "query_run_id": str(query_record.id),
                    "packet_hash": fingerprint,
                },
            )
            return
        if step.step_key == "extract_visual_evidence":
            if provider is None:
                raise RuntimeError("visual_enrichment_provider_required")
            packet = await service.packet_for_query(query_record)
            fingerprint = packet_hash(packet)
            if fingerprint != cursor.get("packet_hash"):
                raise RuntimeError("visual_enrichment_packet_changed")
            result = await provider.extract_visual_evidence(packet)
            result_payload = result.model_dump(mode="json")
            result_hash = hashlib.sha256(result.model_dump_json().encode()).hexdigest()
            now = datetime.now(UTC)
            session.add(
                ModelCallORM(
                    id=uuid4(),
                    pipeline_step_id=step.id,
                    provider=provider.provider,
                    model=provider.model,
                    model_revision=provider.model_revision,
                    request_hash=fingerprint,
                    response_hash=result_hash,
                    provider_request_id=result.provider_request_id,
                    usage=result.usage,
                    pricing_snapshot=None,
                    finish_reason=result.finish_reason,
                    created_at=now,
                    updated_at=now,
                )
            )
            await append_run_event(
                session,
                run_id=run.id,
                event_type="visual_enrichment.extracted",
                payload={
                    "query_run_id": str(query_record.id),
                    "result_hash": result_hash,
                    "draft_count": len(result.observations),
                    "provider_version": provider.version,
                },
            )
            await complete_step_and_enqueue(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor={
                    **cursor,
                    "result_hash": result_hash,
                    "draft_count": len(result.observations),
                    "completed_step_keys": [step.step_key],
                },
                next_step_key="persist_visual_evidence",
                next_cursor={
                    "schema_version": "v1",
                    "request_hash": request_hash,
                    "query_run_id": str(query_record.id),
                    "provider_version": provider.version,
                    "result_hash": result_hash,
                    "result": result_payload,
                },
            )
            return
        if step.step_key != "persist_visual_evidence":
            raise ValueError("unsupported_visual_enrichment_step")
        result = VisualEnrichmentResult.model_validate(cursor.get("result"))
        outcome = await service.persist_result(
            run=run,
            query_run=query_record,
            result=result,
            extractor_version=str(cursor["provider_version"]),
        )
        final_cursor: dict[str, object] = {
            "schema_version": "v1",
            "request_hash": request_hash,
            "query_run_id": str(query_record.id),
            "result_hash": str(cursor["result_hash"]),
            "observation_ids": [str(item) for item in outcome.observation_ids],
            "suggestion_ids": [str(item) for item in outcome.suggestion_ids],
            "rejected_count": outcome.rejected_count,
            "result_status": (
                "facts_persisted"
                if outcome.observation_ids
                else "suggestions_pending"
                if outcome.suggestion_ids
                else "no_valid_results"
            ),
            "completed_step_keys": [step.step_key],
        }
        if outcome.observation_ids:
            await complete_step_and_enqueue(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor=final_cursor,
                next_step_key="aggregate_appearance",
                next_cursor={
                    "schema_version": "v1",
                    "query_run_id": str(query_record.id),
                    "completed_character_ids": [],
                },
            )
        else:
            await append_run_event(
                session,
                run_id=run.id,
                event_type="visual_enrichment.completed",
                payload={
                    "observation_count": 0,
                    "suggestion_count": len(outcome.suggestion_ids),
                    "rejected_count": outcome.rejected_count,
                    "result_status": final_cursor["result_status"],
                },
            )
            await complete_step(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor=final_cursor,
            )
    except Exception as error:
        logger.exception(
            "visual_enrichment.failed",
            extra={"run_id": str(run_id), "step_id": str(step_id)},
        )
        await record_step_error(
            session,
            step_id=step_id,
            run_id=run.id,
            error_code="visual_enrichment_failed",
            error=error,
            max_attempts=max_attempts,
            expected_generation=expected_generation,
        )
        raise
