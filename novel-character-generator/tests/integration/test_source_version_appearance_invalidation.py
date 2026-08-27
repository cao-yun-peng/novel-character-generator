from asyncio import to_thread
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.ports.extraction import (
    ExtractionProvider,
    VisualCandidateExtractionResult,
    VisualEntityCandidate,
    VisualFactCandidate,
)
from novel_character_generator.application.services.appearance_service import (
    AppearanceResolutionError,
    AppearanceService,
    SnapshotTarget,
)
from novel_character_generator.application.services.ingestion_service import IngestionService
from novel_character_generator.infrastructure.db.orm import (
    CharacterAppearanceStateORM,
    CharacterConflictORM,
    CharacterORM,
    CharacterRenderProfileORM,
    FeatureObservationORM,
    SourceDocumentVersionORM,
)
from novel_character_generator.infrastructure.storage.local import LocalArtifactStore
from novel_character_generator.workers.handlers.appearance_aggregation import (
    process_appearance_aggregation_run,
)
from novel_character_generator.workers.handlers.extraction import process_extraction_run
from novel_character_generator.workers.handlers.ingestion import process_ingestion_run
from novel_character_generator.workers.handlers.phase_resolution import (
    process_phase_resolution_run,
)


class VersionedHairProvider:
    version = "versioned-hair-v1"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        for phrase, value in (("黑发", "black"), ("白发", "white")):
            if phrase in text:
                return VisualCandidateExtractionResult(
                    entities=[
                        VisualEntityCandidate(
                            local_id="e1",
                            representative_name="林舟",
                            mention_quote="林舟",
                            mention_kind="name",
                            confidence=1.0,
                        )
                    ],
                    visual_candidates=[
                        VisualFactCandidate(
                            entity_ref="e1",
                            field_path="hair.color",
                            value=value,
                            evidence_quote=phrase,
                            confidence=1.0,
                        )
                    ],
                )
        return VisualCandidateExtractionResult()


class VersionedEyeProvider:
    version = "versioned-eye-v1"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        for phrase, value in (("黑眼", "black"), ("蓝眼", "blue")):
            if phrase in text:
                return VisualCandidateExtractionResult(
                    entities=[
                        VisualEntityCandidate(
                            local_id="e1",
                            representative_name="林舟",
                            mention_quote="林舟",
                            mention_kind="name",
                            confidence=1.0,
                        )
                    ],
                    visual_candidates=[
                        VisualFactCandidate(
                            entity_ref="e1",
                            field_path="face.eye_color",
                            value=value,
                            evidence_quote=phrase,
                            confidence=1.0,
                        )
                    ],
                )
        return VisualCandidateExtractionResult()


async def run_analysis(
    service: IngestionService,
    store: LocalArtifactStore,
    novel_id: UUID,
    idempotency_key: str,
    provider: ExtractionProvider | None = None,
) -> None:
    run = await service.create_analysis_run(novel_id, idempotency_key)
    assert run is not None
    await process_ingestion_run(service.session, store, run.id, target_tokens=1_000)
    await process_extraction_run(
        service.session,
        provider or VersionedHairProvider(),
        run.id,
    )
    await process_phase_resolution_run(service.session, run.id)
    await process_appearance_aggregation_run(service.session, run.id)


@pytest.mark.asyncio
async def test_source_replacement_invalidates_old_truth_and_preserves_approved_history(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'source-invalidation.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "artifacts")

    async with sessions() as session:
        service = IngestionService(session, store)
        novel = await service.upload(filename="story.txt", data="第一章\n林舟是黑发。".encode())
        await run_analysis(service, store, novel.id, "analysis-v1")

        character = await session.scalar(
            select(CharacterORM).where(
                CharacterORM.novel_id == novel.id,
                CharacterORM.canonical_name == "林舟",
            )
        )
        assert character is not None
        appearance = AppearanceService(session)
        first_profile = await appearance.latest_profile(character.id)
        assert first_profile is not None
        first_profile = await appearance.approve(
            character.id,
            expected_revision=first_profile.revision,
            actor_id="editor-1",
        )
        first_profile_id = first_profile.id
        first_profile_revision = first_profile.revision
        first_snapshot = await appearance.snapshot(character.id, target=SnapshotTarget())
        first_state_id = first_profile.appearance_state_ids[0]
        first_observation = await session.scalar(
            select(FeatureObservationORM).where(FeatureObservationORM.character_id == character.id)
        )
        assert first_observation is not None
        first_version = await service.repository.latest_document_version(novel.id)
        assert first_version is not None

        second_version = await service.upload_version(
            novel_id=novel.id,
            filename="story.txt",
            data="第一章\n林舟是白发。".encode(),
        )
        assert second_version is not None and second_version.version == 2
        assert second_version.supersedes_version_id == first_version.id
        await session.refresh(first_observation)
        invalidated_state = await session.get(CharacterAppearanceStateORM, UUID(first_state_id))
        stale_profile = await session.get(CharacterRenderProfileORM, first_profile_id)
        assert first_observation.record_status == "invalidated"
        assert first_observation.valid_to is not None
        assert invalidated_state is not None
        assert invalidated_state.record_status == "invalidated"
        assert stale_profile is not None
        assert stale_profile.status == "approved"
        assert stale_profile.record_status == "stale"
        assert stale_profile.revision == first_profile_revision
        with pytest.raises(AppearanceResolutionError, match="render_profile_stale"):
            await appearance.snapshot(character.id, target=SnapshotTarget())

        await run_analysis(service, store, novel.id, "analysis-v2")
        profiles = list(
            await session.scalars(
                select(CharacterRenderProfileORM)
                .where(CharacterRenderProfileORM.character_id == character.id)
                .order_by(CharacterRenderProfileORM.version)
            )
        )
        assert len(profiles) == 2
        assert profiles[0].id == first_profile_id
        assert profiles[0].status == "approved"
        assert profiles[0].record_status == "stale"
        assert profiles[0].revision == first_profile_revision
        assert profiles[1].version == 2
        assert profiles[1].status == "needs_review"
        assert profiles[1].record_status == "active"
        assert profiles[1].source_document_version_id == second_version.id

        await session.refresh(invalidated_state)
        assert invalidated_state.record_status == "superseded"
        active_states = list(
            await session.scalars(
                select(CharacterAppearanceStateORM).where(
                    CharacterAppearanceStateORM.character_id == character.id,
                    CharacterAppearanceStateORM.record_status == "active",
                )
            )
        )
        assert len(active_states) == 1
        assert active_states[0].appearance["hair"]["color"] == "white"
        active_observations = list(
            await session.scalars(
                select(FeatureObservationORM).where(
                    FeatureObservationORM.character_id == character.id,
                    FeatureObservationORM.record_status == "active",
                )
            )
        )
        assert len(active_observations) == 1
        assert active_observations[0].source_document_version_id == second_version.id
        assert active_observations[0].value == "white"

        protected_conflict = await session.scalar(
            select(CharacterConflictORM).where(
                CharacterConflictORM.character_id == character.id,
                CharacterConflictORM.status == "pending",
            )
        )
        assert protected_conflict is not None
        assert protected_conflict.field_path == "hair.color"
        assert protected_conflict.conflict_kind == "human_confirmation"
        assert set(protected_conflict.candidate_values) == {"black", "white"}
        assert profiles[1].unresolved_conflicts[0]["protects_human_confirmation"] is True
        with pytest.raises(AppearanceResolutionError, match="appearance_conflicts_unresolved"):
            await appearance.approve(
                character.id,
                expected_revision=profiles[1].revision,
                actor_id="editor-1",
            )
        await appearance.resolve_conflict(
            protected_conflict.id,
            selected_value="white",
            expected_revision=protected_conflict.revision,
            actor_id="editor-1",
        )

        second_profile = await appearance.approve(
            character.id,
            expected_revision=profiles[1].revision,
            actor_id="editor-1",
        )
        second_snapshot = await appearance.snapshot(character.id, target=SnapshotTarget())
        assert second_snapshot["appearance"]["hair"]["color"] == "white"
        assert second_snapshot["snapshot_hash"] != first_snapshot["snapshot_hash"]

        same_version = await service.upload_version(
            novel_id=novel.id,
            filename="story.txt",
            data="第一章\n林舟是白发。".encode(),
        )
        assert same_version is not None and same_version.id == second_version.id
        await session.refresh(second_profile)
        assert second_profile.record_status == "active"
        counts_before = (
            await session.scalar(select(func.count()).select_from(SourceDocumentVersionORM)),
            await session.scalar(select(func.count()).select_from(CharacterAppearanceStateORM)),
            await session.scalar(select(func.count()).select_from(CharacterRenderProfileORM)),
        )
        await run_analysis(service, store, novel.id, "analysis-v2-repeat")
        counts_after = (
            await session.scalar(select(func.count()).select_from(SourceDocumentVersionORM)),
            await session.scalar(select(func.count()).select_from(CharacterAppearanceStateORM)),
            await session.scalar(select(func.count()).select_from(CharacterRenderProfileORM)),
        )
        assert counts_after == counts_before

    await engine.dispose()


@pytest.mark.asyncio
async def test_identity_confirmation_conflict_requires_resolution(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'identity-protection.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalArtifactStore(tmp_path / "identity-artifacts")

    async with sessions() as session:
        ingestion = IngestionService(session, store)
        novel = await ingestion.upload(filename="eyes.txt", data="第一章\n林舟是黑眼。".encode())
        await run_analysis(
            ingestion,
            store,
            novel.id,
            "eyes-v1",
            provider=VersionedEyeProvider(),
        )
        character = await session.scalar(
            select(CharacterORM).where(
                CharacterORM.novel_id == novel.id,
                CharacterORM.canonical_name == "林舟",
            )
        )
        assert character is not None
        appearance = AppearanceService(session)
        first_profile = await appearance.latest_profile(character.id)
        assert first_profile is not None
        await appearance.approve(
            character.id,
            expected_revision=first_profile.revision,
            actor_id="editor-1",
        )

        await ingestion.upload_version(
            novel_id=novel.id,
            filename="eyes.txt",
            data="第一章\n林舟是蓝眼。".encode(),
        )
        await run_analysis(
            ingestion,
            store,
            novel.id,
            "eyes-v2",
            provider=VersionedEyeProvider(),
        )
        draft = await appearance.latest_profile(character.id)
        conflict = await session.scalar(
            select(CharacterConflictORM).where(
                CharacterConflictORM.character_id == character.id,
                CharacterConflictORM.status == "pending",
            )
        )
        assert draft is not None and conflict is not None
        assert draft.status == "needs_review"
        assert draft.identity_anchor["face"]["eye_color"] == "black"
        assert conflict.conflict_kind == "human_confirmation"
        assert conflict.appearance_state_ids == []
        assert set(conflict.candidate_values) == {"black", "blue"}

        await appearance.resolve_conflict(
            conflict.id,
            selected_value="blue",
            expected_revision=conflict.revision,
            actor_id="editor-1",
        )
        approved = await appearance.approve(
            character.id,
            expected_revision=draft.revision,
            actor_id="editor-1",
        )
        assert approved.identity_anchor["face"]["eye_color"] == "blue"
        assert approved.field_sources["face.eye_color"] == [f"manual:conflict:{conflict.id}"]
        snapshot = await appearance.snapshot(character.id, target=SnapshotTarget())
        assert snapshot["appearance"]["face"]["eye_color"] == "blue"

    await engine.dispose()
