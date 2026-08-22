from asyncio import to_thread
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from novel_character_generator.api.app import create_app
from novel_character_generator.api.deps import get_session
from novel_character_generator.infrastructure.db.orm import (
    CharacterAppearanceStateORM,
    CharacterEntityOperationORM,
    CharacterORM,
    CharacterRenderProfileORM,
    DecisionRecordORM,
    EventParticipantORM,
    FeatureObservationORM,
    HumanApprovalORM,
    NovelORM,
    PipelineRunORM,
    SceneORM,
    StoryEventORM,
    TimelineORM,
)
from novel_character_generator.settings import get_settings


@pytest.mark.asyncio
async def test_character_merge_and_split_are_audited_idempotent_and_revision_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'entities.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    novel_id = uuid4()
    target_id = uuid4()
    source_id = uuid4()
    timeline_id = uuid4()
    event_id = uuid4()
    scene_id = uuid4()
    source_state_id = uuid4()
    source_observation_id = uuid4()
    extraction_run_id = uuid4()

    async with sessions() as session:
        session.add(
            NovelORM(
                id=novel_id,
                title="Entity operations",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add_all(
            [
                CharacterORM(
                    id=target_id,
                    novel_id=novel_id,
                    canonical_name="Hero",
                    status="active",
                    revision=1,
                    merged_into_character_id=None,
                    created_at=now,
                    updated_at=now,
                ),
                CharacterORM(
                    id=source_id,
                    novel_id=novel_id,
                    canonical_name="Masked Hero",
                    status="active",
                    revision=1,
                    merged_into_character_id=None,
                    created_at=now,
                    updated_at=now,
                ),
                TimelineORM(
                    id=timeline_id,
                    novel_id=novel_id,
                    name="main",
                    parent_timeline_id=None,
                    branch_event_id=None,
                    canonicality="canonical",
                ),
                PipelineRunORM(
                    id=extraction_run_id,
                    novel_id=novel_id,
                    run_type="text_analysis",
                    status="succeeded",
                    idempotency_key="entity-test-extraction",
                    cancel_requested=False,
                    completed_at=now,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.flush()
        session.add(
            StoryEventORM(
                id=event_id,
                timeline_id=timeline_id,
                name="reveal",
                story_order=Decimal("1"),
                starts_at=None,
                ends_at=None,
            )
        )
        await session.flush()
        session.add_all(
            [
                EventParticipantORM(
                    id=uuid4(),
                    event_id=event_id,
                    character_id=target_id,
                    role="actor",
                    evidence_observation_ids=["target-evidence"],
                    created_at=now,
                    updated_at=now,
                ),
                EventParticipantORM(
                    id=uuid4(),
                    event_id=event_id,
                    character_id=source_id,
                    role="actor",
                    evidence_observation_ids=["source-evidence"],
                    created_at=now,
                    updated_at=now,
                ),
                SceneORM(
                    id=scene_id,
                    novel_id=novel_id,
                    timeline_id=timeline_id,
                    event_id=event_id,
                    chapter_ordinal=1,
                    narrative_order=1,
                    point_of_view_character_id=source_id,
                    label="reveal scene",
                    source_document_version_id=None,
                    source_chunk_id=None,
                    char_start=None,
                    char_end=None,
                    presentation_mode="direct",
                    reality_status="canonical",
                    confidence=1.0,
                    binding_status="confirmed",
                    binding_revision=1,
                    created_by_run_id=None,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.flush()
        scope = {
            "timeline_id": str(timeline_id),
            "start_event_id": str(event_id),
            "end_event_id": None,
            "scope_type": "persistent",
            "presentation_mode": "direct",
            "reality_status": "canonical",
        }
        session.add_all(
            [
                CharacterAppearanceStateORM(
                    id=source_state_id,
                    character_id=source_id,
                    temporal_scope=scope,
                    label="revealed",
                    state_kind="persistent_change",
                    merge_priority=20,
                    age_stage="adult",
                    appearance={"face": {"scar": "left cheek"}},
                    field_sources={},
                    resolver_version="appearance-resolver-v1",
                    created_by_run_id=None,
                    record_status="active",
                    status="approved",
                    created_at=now,
                    updated_at=now,
                ),
                FeatureObservationORM(
                    id=source_observation_id,
                    character_id=source_id,
                    field_path="face.scar",
                    value="left cheek",
                    source_kind="manual",
                    source_document_version_id=None,
                    source_chunk_id=None,
                    mention_span_id=None,
                    evidence_quote=None,
                    char_start=None,
                    char_end=None,
                    chapter_ordinal=1,
                    scene_id=scene_id,
                    event_id=event_id,
                    temporal_scope=scope,
                    epistemic_status="asserted",
                    grounding_status="manually_grounded",
                    confidence=1.0,
                    extraction_run_id=extraction_run_id,
                    manual_approval_id=None,
                    extractor_version="manual-v1",
                    supersedes_id=None,
                    fingerprint="f" * 64,
                    valid_from=now,
                    valid_to=None,
                    record_status="active",
                    recorded_at=now,
                    invalidated_at=None,
                    invalidated_by_run_id=None,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.flush()
        session.add(
            CharacterRenderProfileORM(
                id=uuid4(),
                character_id=source_id,
                version=1,
                status="approved",
                identity_anchor={"face": {"shape": "oval"}},
                default_appearance_state_id=source_state_id,
                default_stage_key="revealed",
                appearance_state_ids=[str(source_state_id)],
                palette={},
                field_sources={},
                field_suggestions={},
                unresolved_conflicts=[],
                style_preset="illustration-v1",
                approved_by="editor-0",
                approved_at=now,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    monkeypatch.setenv("USER_API_KEY", "user-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    merge_body = {
        "target_character_id": str(target_id),
        "sources": [{"character_id": str(source_id), "revision": 1}],
        "reason": "The masked identity is explicitly revealed.",
    }
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.post(
                "/api/v1/characters/merge",
                headers={
                    "X-API-Key": "user-secret",
                    "If-Match": '"1"',
                    "Idempotency-Key": "merge-1",
                    "X-Actor-ID": "editor-1",
                },
                json=merge_body,
            )
            assert denied.status_code == 403
            assert denied.json()["code"] == "admin_api_key_required"

            admin_headers = {
                "X-API-Key": "admin-secret",
                "If-Match": '"1"',
                "Idempotency-Key": "merge-1",
                "X-Actor-ID": "editor-1",
            }
            merged = await client.post(
                "/api/v1/characters/merge", headers=admin_headers, json=merge_body
            )
            assert merged.status_code == 200
            assert merged.json()["operation_type"] == "merge"
            assert merged.json()["source_character_ids"] == [str(source_id)]
            assert merged.json()["target_character_ids"] == [str(target_id)]
            merge_operation_id = merged.json()["id"]

            replayed = await client.post(
                "/api/v1/characters/merge", headers=admin_headers, json=merge_body
            )
            assert replayed.status_code == 200
            assert replayed.json()["id"] == merge_operation_id

            changed_replay = await client.post(
                "/api/v1/characters/merge",
                headers=admin_headers,
                json={**merge_body, "reason": "different action"},
            )
            assert changed_replay.status_code == 409
            assert changed_replay.json()["code"] == "entity_operation_idempotency_conflict"

            approved_profile = await client.post(
                f"/api/v1/characters/{target_id}/approve",
                headers={
                    "X-API-Key": "user-secret",
                    "If-Match": '"2"',
                    "X-Actor-ID": "editor-1",
                },
            )
            assert approved_profile.status_code == 200
            assert approved_profile.json()["status"] == "approved"

            split_body = {
                "targets": [
                    {
                        "canonical_name": "Hero A",
                        "reuse_source": True,
                        "assignments": {},
                    },
                    {
                        "canonical_name": "Hero B",
                        "reuse_source": False,
                        "assignments": {
                            "observation_ids": [str(source_observation_id)],
                            "appearance_state_ids": [str(source_state_id)],
                            "scene_ids": [str(scene_id)],
                        },
                    },
                ],
                "invalidate_render_assets": False,
                "reason": "Evidence proves these are two different people.",
            }
            split_headers = {
                "X-API-Key": "admin-secret",
                "If-Match": '"2"',
                "Idempotency-Key": "split-1",
                "X-Actor-ID": "editor-2",
            }
            protected = await client.post(
                f"/api/v1/characters/{target_id}/split",
                headers=split_headers,
                json=split_body,
            )
            assert protected.status_code == 409
            assert protected.json()["code"] == "split_requires_render_asset_invalidation"

            split_body["invalidate_render_assets"] = True
            split_result = await client.post(
                f"/api/v1/characters/{target_id}/split",
                headers=split_headers,
                json=split_body,
            )
            assert split_result.status_code == 200
            assert split_result.json()["operation_type"] == "split"
            assert split_result.json()["target_character_ids"][0] == str(target_id)
            new_character_id = UUID(split_result.json()["target_character_ids"][1])

            split_replay = await client.post(
                f"/api/v1/characters/{target_id}/split",
                headers=split_headers,
                json=split_body,
            )
            assert split_replay.status_code == 200
            assert split_replay.json()["id"] == split_result.json()["id"]

            characters = await client.get(
                f"/api/v1/novels/{novel_id}/characters",
                headers={"X-API-Key": "user-secret"},
            )
            assert characters.status_code == 200
            by_id = {item["id"]: item for item in characters.json()}
            assert by_id[str(source_id)]["status"] == "merged"
            assert by_id[str(source_id)]["merged_into_character_id"] == str(target_id)
            assert by_id[str(target_id)]["canonical_name"] == "Hero A"
            assert by_id[str(target_id)]["revision"] == 3
            assert by_id[str(new_character_id)]["canonical_name"] == "Hero B"
    finally:
        get_settings.cache_clear()

    async with sessions() as session:
        observation = await session.get_one(FeatureObservationORM, source_observation_id)
        state = await session.get_one(CharacterAppearanceStateORM, source_state_id)
        scene = await session.get_one(SceneORM, scene_id)
        source = await session.get_one(CharacterORM, source_id)
        target = await session.get_one(CharacterORM, target_id)
        profile = await session.scalar(
            select(CharacterRenderProfileORM).where(
                CharacterRenderProfileORM.character_id == target_id
            )
        )
        participants = list(
            await session.scalars(
                select(EventParticipantORM).where(EventParticipantORM.event_id == event_id)
            )
        )
        operations = list(await session.scalars(select(CharacterEntityOperationORM)))
        decisions = list(await session.scalars(select(DecisionRecordORM)))
        approvals = list(
            await session.scalars(
                select(HumanApprovalORM).where(
                    HumanApprovalORM.approval_type.in_(("character_merge", "character_split"))
                )
            )
        )
        assert source.status == "merged"
        assert source.merged_into_character_id == target_id
        assert target.canonical_name == "Hero A"
        assert observation.character_id == new_character_id
        assert state.character_id == new_character_id
        assert scene.point_of_view_character_id == new_character_id
        assert profile is not None
        assert profile.status == "needs_review"
        assert profile.appearance_state_ids == []
        assert len(participants) == 1
        assert set(participants[0].evidence_observation_ids) == {
            "target-evidence",
            "source-evidence",
        }
        assert len(operations) == 2
        assert {item.decision_kind for item in decisions} >= {
            "character_merge",
            "character_split",
        }
        assert len(approvals) == 2
        assert all(
            item.status == "approved" and item.pipeline_step_id is None for item in approvals
        )

    await engine.dispose()
