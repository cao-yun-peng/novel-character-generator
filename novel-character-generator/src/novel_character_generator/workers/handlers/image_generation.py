from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_character_generator.application.ports.artifact_store import ArtifactStore
from novel_character_generator.application.ports.image_generation import (
    ImageProvider,
    ImageProviderSubmissionRejected,
    ImageSubmitRequest,
)
from novel_character_generator.application.services.generation_context_service import (
    GenerationContextBuilder,
    ImageRunRequest,
)
from novel_character_generator.domain.entities.image import GenerationMode, ImageRenderSpec
from novel_character_generator.domain.entities.pipeline import ExternalOperationState
from novel_character_generator.infrastructure.db.orm import (
    ArtifactORM,
    ExternalOperationORM,
    GeneratedImageORM,
    GenerationContextORM,
    PipelineRunORM,
    PipelineStepORM,
)
from novel_character_generator.infrastructure.db.repositories.external_operations import (
    ExternalOperationRepository,
)
from novel_character_generator.infrastructure.db.repositories.run_events import append_run_event
from novel_character_generator.workers.task_claim import (
    complete_step,
    complete_step_and_enqueue,
    defer_step,
    mark_cancelled,
    record_step_error,
    start_step,
)


class ImageProviderNotReady(RuntimeError):
    pass


def _request_from_cursor(cursor: dict[str, object]) -> ImageRunRequest:
    raw = cursor.get("request")
    if not isinstance(raw, dict):
        raise ValueError("image_request_cursor_missing")
    raw_generation_mode = str(raw.get("generation_mode", "concept"))
    if raw_generation_mode not in {"concept", "character_design", "consistent_scene"}:
        raise ValueError("invalid_generation_mode_cursor")
    return ImageRunRequest(
        timeline_id=UUID(str(raw["timeline_id"])),
        target_event_id=UUID(str(raw["target_event_id"]))
        if raw.get("target_event_id")
        else None,
        target_scene_id=UUID(str(raw["target_scene_id"]))
        if raw.get("target_scene_id")
        else None,
        target_chapter_ordinal=int(raw["target_chapter_ordinal"])
        if raw.get("target_chapter_ordinal") is not None
        else None,
        stage_keys=[str(item) for item in raw.get("stage_keys", [])],
        candidate_count=int(raw.get("candidate_count", 1)),
        generate_character_sheet=bool(raw.get("generate_character_sheet", False)),
        generation_mode=cast(GenerationMode, raw_generation_mode),
        render_overrides={
            str(key): value for key, value in dict(raw.get("render_overrides", {})).items()
        },
        budget_limit=Decimal(str(raw.get("budget_limit", "0"))),
    )


async def process_image_generation_run(
    session: AsyncSession,
    artifact_store: ArtifactStore,
    provider: ImageProvider,
    run_id: UUID,
    *,
    workflow_profile: str,
    workflow_version: str,
    max_attempts: int = 3,
    poll_interval_seconds: float = 10.0,
) -> None:
    run = await session.get(PipelineRunORM, run_id)
    if run is None or run.run_type != "image_generation":
        raise ValueError("image_generation_run_not_found")
    step = await session.scalar(
        select(PipelineStepORM)
        .where(
            PipelineStepORM.run_id == run_id,
            PipelineStepORM.status.in_(("queued", "retry_scheduled", "claimed")),
        )
        .order_by(PipelineStepORM.created_at)
    )
    if step is None:
        if run.status == "succeeded":
            return
        raise RuntimeError("image_generation_step_not_found")
    if run.cancel_requested:
        await mark_cancelled(
            session,
            step=step,
            run=run,
            expected_generation=step.lease_generation,
        )
        return
    step_id = step.id
    expected_generation = await start_step(session, step=step, run=run)
    cursor = step.cursor or {}
    try:
        if step.step_key == "freeze_generation_context":
            request = _request_from_cursor(cursor)
            context = await GenerationContextBuilder(
                session,
                provider=provider.provider,
                workflow_profile=workflow_profile,
                workflow_version=workflow_version,
            ).freeze(
                run=run,
                character_id=UUID(str(cursor["character_id"])),
                request=request,
            )
            await complete_step_and_enqueue(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor={
                    **cursor,
                    "generation_context_id": str(context.id),
                    "context_hash": context.context_hash,
                    "completed_step_keys": [step.step_key],
                },
                next_step_key="submit_image",
                next_cursor={
                    "schema_version": "v1",
                    "generation_context_id": str(context.id),
                },
            )
            return
        context = await session.get_one(
            GenerationContextORM, UUID(str(cursor["generation_context_id"]))
        )
        if step.step_key == "submit_image":
            operation_ids = await _submit_candidates(
                session,
                provider=provider,
                run=run,
                step=step,
                context=context,
                lease_generation=expected_generation,
            )
            await complete_step_and_enqueue(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor={
                    **cursor,
                    "operation_ids": [str(item) for item in operation_ids],
                    "completed_step_keys": [step.step_key],
                },
                next_step_key="poll_image",
                next_cursor={
                    "schema_version": "v1",
                    "generation_context_id": str(context.id),
                    "operation_ids": [str(item) for item in operation_ids],
                },
            )
            return
        operation_ids = [UUID(str(item)) for item in cursor.get("operation_ids", [])]
        if step.step_key == "poll_image":
            artifact_refs = await _poll_candidates(session, provider, operation_ids)
            await complete_step_and_enqueue(
                session,
                step=step,
                run=run,
                expected_generation=expected_generation,
                cursor={
                    **cursor,
                    "artifact_refs": artifact_refs,
                    "completed_step_keys": [step.step_key],
                },
                next_step_key="persist_image",
                next_cursor={
                    "schema_version": "v1",
                    "generation_context_id": str(context.id),
                    "operation_ids": [str(item) for item in operation_ids],
                    "artifact_refs": artifact_refs,
                },
            )
            return
        if step.step_key != "persist_image":
            raise ValueError("unsupported_image_generation_step")
        image_ids = await _persist_candidates(
            session,
            artifact_store=artifact_store,
            provider=provider,
            run=run,
            context=context,
            operation_ids=operation_ids,
            artifact_refs={
                str(key): str(value)
                for key, value in dict(cursor.get("artifact_refs", {})).items()
            },
        )
        context.status = "completed"
        context.updated_at = datetime.now(UTC)
        await append_run_event(
            session,
            run_id=run.id,
            event_type="artifact.persisted",
            payload={
                "generation_context_id": str(context.id),
                "image_ids": [str(item) for item in image_ids],
                "context_hash": context.context_hash,
            },
        )
        await complete_step(
            session,
            step=step,
            run=run,
            expected_generation=expected_generation,
            cursor={
                **cursor,
                "generated_image_ids": [str(item) for item in image_ids],
                "completed_step_keys": [step.step_key],
            },
        )
    except ImageProviderNotReady:
        await defer_step(
            session,
            step_id=step_id,
            run_id=run.id,
            expected_generation=expected_generation,
            delay_seconds=poll_interval_seconds,
            reason="image_provider_not_ready",
        )
        return
    except Exception as error:
        await record_step_error(
            session,
            step_id=step_id,
            run_id=run.id,
            error_code="image_generation_failed",
            error=error,
            max_attempts=max_attempts,
            expected_generation=expected_generation,
        )
        raise


async def _submit_candidates(
    session: AsyncSession,
    *,
    provider: ImageProvider,
    run: PipelineRunORM,
    step: PipelineStepORM,
    context: GenerationContextORM,
    lease_generation: int,
) -> list[UUID]:
    repository = ExternalOperationRepository(session)
    operation_ids: list[UUID] = []
    render_spec = ImageRenderSpec.model_validate(
        context.context_payload.get("image_render_spec")
    )
    for candidate_index in range(context.candidate_count):
        request = ImageSubmitRequest(
            context_hash=context.context_hash,
            workflow_profile=context.workflow_profile,
            workflow_version=context.workflow_version,
            candidate_index=candidate_index,
            seed=candidate_index,
            render_spec=render_spec,
        )
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        operation = await repository.prepare(
            run_id=run.id,
            step_id=step.id,
            provider=provider.provider,
            operation_kind="image_generation",
            idempotency_key=(
                f"{context.context_hash}:{context.workflow_version}:{candidate_index}:0"
            ),
            request_fingerprint=fingerprint,
            lease_generation=lease_generation,
        )
        operation_ids.append(operation.id)
        state = ExternalOperationState(operation.status)
        if state == ExternalOperationState.PREPARED:
            operation = await repository.transition(
                operation.id,
                target=ExternalOperationState.SUBMITTING,
                expected_generation=operation.lease_generation,
            )
            await session.commit()
            state = ExternalOperationState(operation.status)
        if state == ExternalOperationState.SUBMITTING:
            try:
                submission = await provider.submit(request)
            except ImageProviderSubmissionRejected:
                await repository.transition(
                    operation.id,
                    target=ExternalOperationState.FAILED,
                    expected_generation=operation.lease_generation,
                )
                await append_run_event(
                    session,
                    run_id=run.id,
                    event_type="provider.operation.submit_rejected",
                    payload={
                        "operation_id": str(operation.id),
                        "candidate_index": candidate_index,
                        "request_fingerprint": fingerprint,
                    },
                )
                await session.commit()
                raise
            except Exception:
                await repository.transition(
                    operation.id,
                    target=ExternalOperationState.SUBMISSION_UNKNOWN,
                    expected_generation=operation.lease_generation,
                )
                await append_run_event(
                    session,
                    run_id=run.id,
                    event_type="provider.operation.submit_unknown",
                    payload={
                        "operation_id": str(operation.id),
                        "candidate_index": candidate_index,
                        "request_fingerprint": fingerprint,
                    },
                )
                await session.commit()
                raise
            await repository.transition(
                operation.id,
                target=ExternalOperationState.SUBMITTED,
                expected_generation=operation.lease_generation,
                provider_request_id=submission.provider_request_id,
                result_refs=submission.artifact_refs,
                response_hash=hashlib.sha256(submission.model_dump_json().encode()).hexdigest(),
            )
            await append_run_event(
                session,
                run_id=run.id,
                event_type="provider.operation.submit_succeeded",
                payload={
                    "operation_id": str(operation.id),
                    "candidate_index": candidate_index,
                    "provider_request_id": submission.provider_request_id,
                },
            )
            await session.commit()
        elif state in {
            ExternalOperationState.SUBMISSION_UNKNOWN,
            ExternalOperationState.MANUAL_REVIEW,
            ExternalOperationState.FAILED,
            ExternalOperationState.CANCELLED,
        }:
            raise RuntimeError(f"image_operation_not_submittable:{state.value}")
    return operation_ids


async def _poll_candidates(
    session: AsyncSession,
    provider: ImageProvider,
    operation_ids: list[UUID],
) -> dict[str, str]:
    repository = ExternalOperationRepository(session)
    artifact_refs: dict[str, str] = {}
    for operation_id in operation_ids:
        operation = await session.get_one(ExternalOperationORM, operation_id)
        state = ExternalOperationState(operation.status)
        if state == ExternalOperationState.SUCCEEDED:
            continue
        if state == ExternalOperationState.SUBMITTED:
            operation = await repository.transition(
                operation.id,
                target=ExternalOperationState.POLLING,
                expected_generation=operation.lease_generation,
            )
            await session.commit()
        if operation.result_refs:
            artifact_refs[str(operation.id)] = operation.result_refs[0]
            continue
        if operation.provider_request_id is None:
            raise RuntimeError("image_provider_request_id_missing")
        remote = await provider.query(operation.provider_request_id)
        if remote.status == "failed":
            await repository.transition(
                operation.id,
                target=ExternalOperationState.FAILED,
                expected_generation=operation.lease_generation,
            )
            await session.commit()
            raise RuntimeError(remote.error_code or "image_provider_failed")
        if remote.status != "succeeded" or not remote.artifact_refs:
            raise ImageProviderNotReady("image_provider_not_ready")
        artifact_refs[str(operation.id)] = remote.artifact_refs[0]
    return artifact_refs


async def _persist_candidates(
    session: AsyncSession,
    *,
    artifact_store: ArtifactStore,
    provider: ImageProvider,
    run: PipelineRunORM,
    context: GenerationContextORM,
    operation_ids: list[UUID],
    artifact_refs: dict[str, str],
) -> list[UUID]:
    repository = ExternalOperationRepository(session)
    image_ids: list[UUID] = []
    existing_images = list(
        await session.scalars(
            select(GeneratedImageORM).where(GeneratedImageORM.run_id == run.id)
        )
    )
    existing_by_index = {
        int(image.evaluation["candidate_index"]): image
        for image in existing_images
        if image.evaluation is not None and "candidate_index" in image.evaluation
    }
    for candidate_index, operation_id in enumerate(operation_ids):
        operation = await session.get_one(ExternalOperationORM, operation_id)
        existing = existing_by_index.get(candidate_index)
        if existing is not None:
            image_ids.append(existing.id)
            continue
        artifact_ref = artifact_refs.get(str(operation.id))
        if artifact_ref is None:
            raise RuntimeError("image_artifact_ref_missing")
        data = await provider.download(artifact_ref)
        if len(data) > 20_000_000:
            raise ValueError("image_artifact_too_large")
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("image_artifact_invalid_png")
        content_hash = hashlib.sha256(data).hexdigest()
        storage_uri = await artifact_store.put(content_hash=content_hash, data=data)
        artifact = await session.scalar(
            select(ArtifactORM).where(ArtifactORM.content_hash == content_hash)
        )
        now = datetime.now(UTC)
        if artifact is None:
            artifact = ArtifactORM(
                id=uuid4(),
                content_hash=content_hash,
                mime_type="image/png",
                storage_uri=storage_uri,
                byte_size=len(data),
                artifact_kind="generated_image",
                created_at=now,
                updated_at=now,
            )
            session.add(artifact)
            await session.flush()
        image = GeneratedImageORM(
            id=uuid4(),
            character_id=context.character_id,
            run_id=run.id,
            artifact_id=artifact.id,
            workflow_profile=context.workflow_profile,
            workflow_version=context.workflow_version,
            snapshot_hash=context.snapshot_hash,
            evaluation={
                "candidate_index": candidate_index,
                "context_hash": context.context_hash,
                "provider": provider.provider,
                "provider_version": provider.version,
                "prompt_renderer": provider.prompt_renderer,
                "prompt_renderer_version": provider.prompt_renderer_version,
                "provider_request_id": operation.provider_request_id,
                "mock": provider.provider == "mock",
            },
            created_at=now,
            updated_at=now,
        )
        session.add(image)
        await session.flush()
        operation.artifact_id = artifact.id
        await repository.transition(
            operation.id,
            target=ExternalOperationState.SUCCEEDED,
            expected_generation=operation.lease_generation,
            response_hash=content_hash,
        )
        image_ids.append(image.id)
    return image_ids
