from asyncio import to_thread
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.image_generation import (
    ImageRemoteStatus,
    ImageSubmission,
    ImageSubmitRequest,
)
from novel_character_generator.application.services.generation_context_service import (
    ImageRunRequest,
    ImageRunService,
)
from novel_character_generator.infrastructure.db.orm import (
    ArtifactORM,
    CharacterAppearanceStateORM,
    CharacterORM,
    CharacterRenderProfileORM,
    ExternalOperationORM,
    GeneratedImageORM,
    GenerationContextORM,
    NovelORM,
    PipelineRunORM,
    PipelineStepORM,
    TimelineORM,
)
from novel_character_generator.infrastructure.image.mock import MockImageProvider
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.workers.handlers.image_generation import (
    process_image_generation_run,
)


class UnknownSubmissionMockProvider(MockImageProvider):
    def __init__(self) -> None:
        self.submit_calls = 0

    async def submit(self, request: ImageSubmitRequest) -> ImageSubmission:
        self.submit_calls += 1
        raise RuntimeError("simulated_submit_timeout")


class PendingOnceMockProvider(MockImageProvider):
    def __init__(self) -> None:
        self.query_calls = 0

    async def submit(self, request: ImageSubmitRequest) -> ImageSubmission:
        submission = await super().submit(request)
        return ImageSubmission(
            provider_request_id=submission.provider_request_id,
            status="submitted",
        )

    async def query(self, provider_request_id: str) -> ImageRemoteStatus:
        self.query_calls += 1
        if self.query_calls == 1:
            return ImageRemoteStatus(status="running")
        return await super().query(provider_request_id)


@pytest.mark.asyncio
async def test_generation_context_and_mock_provider_are_deterministic_and_recoverable(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'image-generation.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")
    now = datetime.now(UTC)
    novel_id = uuid4()
    character_id = uuid4()
    timeline_id = uuid4()
    state_id = uuid4()
    profile_id = uuid4()

    async with sessions() as session:
        session.add(
            NovelORM(
                id=novel_id,
                title="Generic novel",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add(
            CharacterORM(
                id=character_id,
                novel_id=novel_id,
                canonical_name="Lin Zhou",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TimelineORM(
                id=timeline_id,
                novel_id=novel_id,
                name="main",
                parent_timeline_id=None,
                branch_event_id=None,
                canonicality="canonical",
            )
        )
        await session.flush()
        session.add(
            CharacterAppearanceStateORM(
                id=state_id,
                character_id=character_id,
                temporal_scope={
                    "timeline_id": str(timeline_id),
                    "scope_type": "persistent",
                    "start_chapter_ordinal": 1,
                    "presentation_mode": "direct",
                    "reality_status": "canonical",
                    "life_phase_key": "academy_years",
                },
                label="academy years",
                state_kind="base_age_stage",
                merge_priority=10,
                age_stage="adolescence",
                appearance={
                    "age_stage": "adolescence",
                    "hair": {"color": "black", "length": "short"},
                    "clothing": {"style": "school uniform", "color": "blue"},
                },
                field_sources={},
                resolver_version="appearance-resolver-v2",
                created_by_run_id=None,
                record_status="active",
                status="approved",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add(
            CharacterRenderProfileORM(
                id=profile_id,
                character_id=character_id,
                version=1,
                status="approved",
                identity_anchor={"face": {"shape": "oval"}},
                default_appearance_state_id=state_id,
                default_stage_key="academy_years",
                appearance_state_ids=[str(state_id)],
                palette={},
                field_sources={},
                field_suggestions={},
                unresolved_conflicts=[],
                style_preset="illustration-v1",
                approved_by="reviewer",
                approved_at=now,
                revision=2,
                record_status="active",
                input_fingerprint="a" * 64,
                source_document_version_id=None,
                aggregation_run_id=None,
                aggregation_metadata=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

        request = ImageRunRequest(
            timeline_id=timeline_id,
            target_chapter_ordinal=1,
            stage_keys=["academy_years"],
            candidate_count=2,
            budget_limit=Decimal("0"),
        )
        service = ImageRunService(
            session,
            provider="mock",
            workflow_profile="mock-character-portrait",
            workflow_version="1",
            candidate_count_max=4,
        )
        run = await service.create_run(
            character_id=character_id,
            request=request,
            idempotency_key="mock-image-run-1",
        )
        for _ in range(4):
            # A fresh provider instance demonstrates deterministic recovery
            # without in-memory remote job state.
            await process_image_generation_run(
                session,
                store,
                MockImageProvider(),
                run.id,
                workflow_profile="mock-character-portrait",
                workflow_version="1",
            )
        await process_image_generation_run(
            session,
            store,
            MockImageProvider(),
            run.id,
            workflow_profile="mock-character-portrait",
            workflow_version="1",
        )
        await session.refresh(run)
        assert run.status == "succeeded"
        context = await session.scalar(
            select(GenerationContextORM).where(GenerationContextORM.run_id == run.id)
        )
        assert context is not None
        assert context.status == "completed"
        assert len(context.context_hash) == 64
        assert context.context_payload["generation_mode"] == "concept"
        assert context.context_payload["render_readiness"] == {
            "concept_ready": True,
            "character_design_ready": False,
            "consistent_scene_ready": False,
            "blocking_conflict_ids": [],
            "blocking_design_gaps": [
                {
                    "field_path": "field_provenance",
                    "state": "unknown",
                    "importance": "blocking",
                    "target_stage_key": None,
                    "candidate_suggestion_ids": [],
                    "resolution_source": None,
                }
            ],
            "missing_scene_fields": ["environment", "art_direction", "composition"],
            "missing_reference_roles": ["identity"],
            "policy_version": "render-readiness-v1",
        }
        render_spec = context.context_payload["image_render_spec"]
        assert render_spec["schema_version"] == "image-render-spec-v1"
        assert render_spec["render_layout"] == "single_image"
        assert len(render_spec["spec_hash"]) == 64
        assert render_spec["identity_prompt_block"] == [
            "face.shape: oval",
            "hair.color: black",
            "hair.length: short",
        ]
        assert render_spec["stage_prompt_block"] == ["age_stage: adolescence"]
        assert render_spec["outfit_prompt_block"] == [
            "clothing.color: blue",
            "clothing.style: school uniform",
        ]
        assert render_spec["art_direction_prompt_block"] == [
            "style_preset: illustration-v1"
        ]
        assert await session.scalar(
            select(func.count())
            .select_from(GeneratedImageORM)
            .where(GeneratedImageORM.run_id == run.id)
        ) == 2
        assert await session.scalar(select(func.count()).select_from(ArtifactORM)) == 1
        operations = list(
            await session.scalars(
                select(ExternalOperationORM).where(ExternalOperationORM.run_id == run.id)
            )
        )
        assert len(operations) == 2
        assert {item.status for item in operations} == {"succeeded"}
        assert all(item.result_refs for item in operations)
        generated = await session.scalar(
            select(GeneratedImageORM).where(GeneratedImageORM.run_id == run.id)
        )
        assert generated is not None
        assert generated.evaluation["provider"] == "mock"
        assert generated.evaluation["provider_version"] == "mock-image-v1"
        assert generated.evaluation["prompt_renderer"] == "none"
        assert generated.evaluation["prompt_renderer_version"] == "none"

        pending_request = ImageRunRequest(
            timeline_id=timeline_id,
            target_chapter_ordinal=1,
            stage_keys=["academy_years"],
            candidate_count=1,
            render_overrides={"action": "pending-once"},
            budget_limit=Decimal("0"),
        )
        pending_run = await service.create_run(
            character_id=character_id,
            request=pending_request,
            idempotency_key="mock-image-run-pending",
        )
        pending_provider = PendingOnceMockProvider()
        for _ in range(3):
            await process_image_generation_run(
                session,
                store,
                pending_provider,
                pending_run.id,
                workflow_profile="mock-character-portrait",
                workflow_version="1",
                poll_interval_seconds=1,
            )
        poll_step = await session.scalar(
            select(PipelineStepORM).where(
                PipelineStepORM.run_id == pending_run.id,
                PipelineStepORM.step_key == "poll_image",
            )
        )
        assert poll_step is not None
        assert poll_step.status == "retry_scheduled"
        assert poll_step.attempt == 0
        for _ in range(2):
            await process_image_generation_run(
                session,
                store,
                pending_provider,
                pending_run.id,
                workflow_profile="mock-character-portrait",
                workflow_version="1",
                poll_interval_seconds=1,
            )
        await session.refresh(pending_run)
        assert pending_run.status == "succeeded"
        assert pending_provider.query_calls == 2

        second = await service.create_run(
            character_id=character_id,
            request=request,
            idempotency_key="mock-image-run-2",
        )
        await process_image_generation_run(
            session,
            store,
            MockImageProvider(),
            second.id,
            workflow_profile="mock-character-portrait",
            workflow_version="1",
        )
        second_context = await session.scalar(
            select(GenerationContextORM).where(GenerationContextORM.run_id == second.id)
        )
        assert second_context is not None
        assert second_context.context_hash == context.context_hash
        assert second_context.id != context.id

        duplicate = await service.create_run(
            character_id=character_id,
            request=request,
            idempotency_key="mock-image-run-1",
        )
        assert duplicate.id == run.id
        assert await session.scalar(
            select(func.count())
            .select_from(PipelineRunORM)
            .where(PipelineRunORM.run_type == "image_generation")
        ) == 3

        unknown_request = ImageRunRequest(
            timeline_id=timeline_id,
            target_chapter_ordinal=1,
            stage_keys=["academy_years"],
            candidate_count=2,
            render_overrides={"action": "timeout-case"},
            budget_limit=Decimal("0"),
        )
        unknown_run = await service.create_run(
            character_id=character_id,
            request=unknown_request,
            idempotency_key="mock-image-run-unknown",
        )
        failing_provider = UnknownSubmissionMockProvider()
        await process_image_generation_run(
            session,
            store,
            failing_provider,
            unknown_run.id,
            workflow_profile="mock-character-portrait",
            workflow_version="1",
        )
        with pytest.raises(RuntimeError, match="simulated_submit_timeout"):
            await process_image_generation_run(
                session,
                store,
                failing_provider,
                unknown_run.id,
                workflow_profile="mock-character-portrait",
                workflow_version="1",
            )
        unknown_operation = await session.scalar(
            select(ExternalOperationORM).where(
                ExternalOperationORM.run_id == unknown_run.id
            )
        )
        assert unknown_operation is not None
        assert unknown_operation.status == "submission_unknown"
        with pytest.raises(RuntimeError, match="image_operation_not_submittable"):
            await process_image_generation_run(
                session,
                store,
                failing_provider,
                unknown_run.id,
                workflow_profile="mock-character-portrait",
                workflow_version="1",
            )
        assert failing_provider.submit_calls == 1

    await engine.dispose()
