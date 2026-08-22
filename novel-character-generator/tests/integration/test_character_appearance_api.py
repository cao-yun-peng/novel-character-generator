from asyncio import to_thread
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from novel_character_generator.api.app import create_app
from novel_character_generator.api.deps import get_session
from novel_character_generator.infrastructure.db.orm import (
    CharacterAppearanceStateORM,
    CharacterORM,
    NovelORM,
    StoryEventORM,
    TimelineORM,
)
from novel_character_generator.settings import get_settings


@pytest.mark.asyncio
async def test_render_profile_conflict_resolution_and_temporal_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'appearance.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    novel_id = uuid4()
    character_id = uuid4()
    root_timeline_id = uuid4()
    child_timeline_id = uuid4()
    branch_event_id = uuid4()
    future_event_id = uuid4()
    target_event_id = uuid4()
    first_state_id = uuid4()
    second_state_id = uuid4()
    future_state_id = uuid4()
    shared_scope = {
        "timeline_id": str(root_timeline_id),
        "start_event_id": str(branch_event_id),
        "end_event_id": None,
        "start_scene_order": None,
        "end_scene_order": None,
        "start_chapter_ordinal": None,
        "end_chapter_ordinal": None,
        "scope_type": "persistent",
        "presentation_mode": "direct",
        "reality_status": "canonical",
    }

    async with sessions() as session:
        session.add(
            NovelORM(
                id=novel_id,
                title="Appearance test",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add_all(
            [
                CharacterORM(
                    id=character_id,
                    novel_id=novel_id,
                    canonical_name="Lin Zhou",
                    status="active",
                    created_at=now,
                    updated_at=now,
                ),
                TimelineORM(
                    id=root_timeline_id,
                    novel_id=novel_id,
                    name="main",
                    parent_timeline_id=None,
                    branch_event_id=None,
                    canonicality="canonical",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                StoryEventORM(
                    id=branch_event_id,
                    timeline_id=root_timeline_id,
                    name="branch",
                    story_order=Decimal("10"),
                    starts_at=None,
                    ends_at=None,
                ),
                StoryEventORM(
                    id=future_event_id,
                    timeline_id=root_timeline_id,
                    name="after branch",
                    story_order=Decimal("15"),
                    starts_at=None,
                    ends_at=None,
                ),
            ]
        )
        await session.flush()
        session.add(
            TimelineORM(
                id=child_timeline_id,
                novel_id=novel_id,
                name="branch timeline",
                parent_timeline_id=root_timeline_id,
                branch_event_id=branch_event_id,
                canonicality="alternate",
            )
        )
        await session.flush()
        session.add(
            StoryEventORM(
                id=target_event_id,
                timeline_id=child_timeline_id,
                name="target",
                story_order=Decimal("20"),
                starts_at=None,
                ends_at=None,
            )
        )
        session.add_all(
            [
                CharacterAppearanceStateORM(
                    id=first_state_id,
                    character_id=character_id,
                    temporal_scope=shared_scope,
                    label="black hair",
                    state_kind="base_age_stage",
                    merge_priority=10,
                    age_stage="adult",
                    appearance={"hair": {"color": "black"}},
                    field_sources={},
                    resolver_version="appearance-resolver-v1",
                    created_by_run_id=None,
                    record_status="active",
                    status="approved",
                    created_at=now,
                    updated_at=now,
                ),
                CharacterAppearanceStateORM(
                    id=second_state_id,
                    character_id=character_id,
                    temporal_scope=shared_scope,
                    label="brown hair",
                    state_kind="base_age_stage",
                    merge_priority=10,
                    age_stage="adult",
                    appearance={"hair": {"color": "brown"}},
                    field_sources={},
                    resolver_version="appearance-resolver-v1",
                    created_by_run_id=None,
                    record_status="active",
                    status="approved",
                    created_at=now,
                    updated_at=now,
                ),
                CharacterAppearanceStateORM(
                    id=future_state_id,
                    character_id=character_id,
                    temporal_scope={**shared_scope, "start_event_id": str(future_event_id)},
                    label="future scar",
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
            ]
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
    headers = {"X-API-Key": "user-secret"}
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_profile = await client.put(
                f"/api/v1/characters/{character_id}/render-profile",
                headers={**headers, "If-Match": '"0"'},
                json={
                    "identity_anchor": {"face": {"shape": "oval"}},
                    "default_stage_key": "adult",
                    "appearance_state_ids": [
                        str(first_state_id),
                        str(second_state_id),
                        str(future_state_id),
                    ],
                    "palette": {"primary": "blue"},
                    "field_sources": {},
                    "field_suggestions": {},
                    "style_preset": "illustration-v1",
                },
            )
            assert create_profile.status_code == 200
            assert create_profile.headers["etag"] == '"1"'
            assert create_profile.json()["status"] == "needs_review"
            assert len(create_profile.json()["unresolved_conflicts"]) == 1

            conflicts = await client.get(
                f"/api/v1/characters/{character_id}/conflicts", headers=headers
            )
            assert conflicts.status_code == 200
            assert conflicts.json()[0]["field_path"] == "hair.color"
            conflict_id = conflicts.json()[0]["id"]

            blocked_approval = await client.post(
                f"/api/v1/characters/{character_id}/approve",
                headers={**headers, "If-Match": '"1"', "X-Actor-ID": "editor-1"},
            )
            assert blocked_approval.status_code == 409
            assert blocked_approval.json()["code"] == "appearance_conflicts_unresolved"

            resolved = await client.post(
                f"/api/v1/conflicts/{conflict_id}/resolve",
                headers={**headers, "If-Match": '"1"', "X-Actor-ID": "editor-1"},
                json={"selected_value": "auburn"},
            )
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "resolved"
            assert resolved.json()["revision"] == 2

            approved = await client.post(
                f"/api/v1/characters/{character_id}/approve",
                headers={**headers, "If-Match": '"2"', "X-Actor-ID": "editor-1"},
            )
            assert approved.status_code == 200
            assert approved.json()["status"] == "approved"
            assert approved.json()["revision"] == 3

            snapshot = await client.get(
                f"/api/v1/characters/{character_id}/snapshot",
                headers=headers,
                params={"event_id": str(target_event_id)},
            )
            assert snapshot.status_code == 200
            assert snapshot.json()["appearance"]["hair"]["color"] == "auburn"
            assert snapshot.json()["appearance"]["face"]["shape"] == "oval"
            assert "scar" not in snapshot.json()["appearance"]["face"]
            assert snapshot.json()["target"]["timeline_id"] == str(child_timeline_id)
            assert len(snapshot.json()["snapshot_hash"]) == 64

            ambiguous = await client.get(
                f"/api/v1/characters/{character_id}/snapshot", headers=headers
            )
            assert ambiguous.status_code == 409
            assert ambiguous.json()["code"] == "ambiguous_appearance_state"

            stale_update = await client.put(
                f"/api/v1/characters/{character_id}/render-profile",
                headers={**headers, "If-Match": '"2"'},
                json={
                    "identity_anchor": {},
                    "appearance_state_ids": [],
                    "style_preset": "illustration-v1",
                },
            )
            assert stale_update.status_code == 409
            assert stale_update.json()["code"] == "render_profile_revision_conflict"

            next_version = await client.put(
                f"/api/v1/characters/{character_id}/render-profile",
                headers={**headers, "If-Match": '"3"'},
                json={
                    "identity_anchor": {"face": {"shape": "oval"}},
                    "appearance_state_ids": [str(first_state_id)],
                    "style_preset": "illustration-v2",
                },
            )
            assert next_version.status_code == 200
            assert next_version.json()["version"] == 2
            assert next_version.json()["revision"] == 4
            assert next_version.json()["status"] == "draft"
            assert next_version.headers["etag"] == '"4"'
    finally:
        get_settings.cache_clear()
        await engine.dispose()
