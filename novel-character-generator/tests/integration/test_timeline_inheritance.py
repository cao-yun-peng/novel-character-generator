from asyncio import to_thread
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_character_generator.application.services.appearance_service import (
    AppearanceService,
    SnapshotTarget,
)
from novel_character_generator.domain.policies.appearance_aggregation import RESOLVER_VERSION
from novel_character_generator.infrastructure.db.orm import (
    CharacterAppearanceStateORM,
    CharacterORM,
    CharacterRenderProfileORM,
    NovelORM,
    StoryEventORM,
    TimelineORM,
)


def scope(timeline_id: UUID, event_id: UUID) -> dict[str, Any]:
    return {
        "timeline_id": str(timeline_id),
        "start_event_id": str(event_id),
        "scope_type": "persistent",
        "presentation_mode": "direct",
        "reality_status": "canonical",
    }


@pytest.mark.asyncio
async def test_child_timeline_inherits_parent_until_branch_then_evolves_independently(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'timeline-inheritance.db'}"
    config = Config("alembic.ini")
    config.cmd_opts = type("Options", (), {"x": [f"database_url={database_url}"]})()
    await to_thread(command.upgrade, config, "head")
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    novel_id = uuid4()
    character_id = uuid4()
    root_id = uuid4()
    child_id = uuid4()
    before_id = uuid4()
    branch_id = uuid4()
    root_future_id = uuid4()
    child_target_id = uuid4()
    parent_hair_id = uuid4()
    parent_future_id = uuid4()
    child_hair_id = uuid4()

    async with sessions() as session:
        session.add(
            NovelORM(
                id=novel_id,
                title="Timeline inheritance",
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
                id=root_id,
                novel_id=novel_id,
                name="main",
                parent_timeline_id=None,
                branch_event_id=None,
                canonicality="canonical",
            )
        )
        await session.flush()
        session.add_all(
            [
                StoryEventORM(
                    id=before_id,
                    timeline_id=root_id,
                    name="before",
                    story_order=Decimal("5"),
                    starts_at=None,
                    ends_at=None,
                ),
                StoryEventORM(
                    id=branch_id,
                    timeline_id=root_id,
                    name="branch",
                    story_order=Decimal("10"),
                    starts_at=None,
                    ends_at=None,
                ),
                StoryEventORM(
                    id=root_future_id,
                    timeline_id=root_id,
                    name="root future",
                    story_order=Decimal("15"),
                    starts_at=None,
                    ends_at=None,
                ),
            ]
        )
        await session.flush()
        session.add(
            TimelineORM(
                id=child_id,
                novel_id=novel_id,
                name="alternate",
                parent_timeline_id=root_id,
                branch_event_id=branch_id,
                canonicality="alternate",
            )
        )
        await session.flush()
        session.add(
            StoryEventORM(
                id=child_target_id,
                timeline_id=child_id,
                name="child target",
                story_order=Decimal("20"),
                starts_at=None,
                ends_at=None,
            )
        )
        session.add_all(
            [
                CharacterAppearanceStateORM(
                    id=parent_hair_id,
                    character_id=character_id,
                    temporal_scope=scope(root_id, before_id),
                    label="parent black hair",
                    state_kind="base_age_stage",
                    merge_priority=10,
                    age_stage=None,
                    appearance={"hair": {"color": "black"}},
                    field_sources={},
                    resolver_version=RESOLVER_VERSION,
                    aggregation_fingerprint=None,
                    created_by_run_id=None,
                    record_status="active",
                    status="approved",
                    created_at=now,
                    updated_at=now,
                ),
                CharacterAppearanceStateORM(
                    id=parent_future_id,
                    character_id=character_id,
                    temporal_scope=scope(root_id, root_future_id),
                    label="parent future scar",
                    state_kind="persistent_change",
                    merge_priority=20,
                    age_stage=None,
                    appearance={"face": {"scar": "left cheek"}},
                    field_sources={},
                    resolver_version=RESOLVER_VERSION,
                    aggregation_fingerprint=None,
                    created_by_run_id=None,
                    record_status="active",
                    status="approved",
                    created_at=now,
                    updated_at=now,
                ),
                CharacterAppearanceStateORM(
                    id=child_hair_id,
                    character_id=character_id,
                    temporal_scope=scope(child_id, child_target_id),
                    label="child white hair",
                    state_kind="base_age_stage",
                    merge_priority=10,
                    age_stage=None,
                    appearance={"hair": {"color": "white"}},
                    field_sources={},
                    resolver_version=RESOLVER_VERSION,
                    aggregation_fingerprint=None,
                    created_by_run_id=None,
                    record_status="active",
                    status="approved",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.add(
            CharacterRenderProfileORM(
                id=uuid4(),
                character_id=character_id,
                version=1,
                status="approved",
                identity_anchor={},
                default_appearance_state_id=None,
                default_stage_key=None,
                appearance_state_ids=[
                    str(parent_hair_id),
                    str(parent_future_id),
                    str(child_hair_id),
                ],
                palette={},
                field_sources={},
                field_suggestions={},
                unresolved_conflicts=[],
                style_preset="illustration-v1",
                approved_by="editor-1",
                approved_at=now,
                revision=1,
                record_status="active",
                input_fingerprint=None,
                source_document_version_id=None,
                aggregation_run_id=None,
                aggregation_metadata=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

        appearance = AppearanceService(session)
        child_snapshot = await appearance.snapshot(
            character_id,
            target=SnapshotTarget(event_id=child_target_id),
        )
        assert child_snapshot["appearance"]["hair"]["color"] == "white"
        assert "scar" not in child_snapshot["appearance"].get("face", {})
        assert set(child_snapshot["appearance_state_ids"]) == {
            str(parent_hair_id),
            str(child_hair_id),
        }

        root_snapshot = await appearance.snapshot(
            character_id,
            target=SnapshotTarget(event_id=root_future_id),
        )
        assert root_snapshot["appearance"]["hair"]["color"] == "black"
        assert root_snapshot["appearance"]["face"]["scar"] == "left cheek"
        assert str(child_hair_id) not in root_snapshot["appearance_state_ids"]

    await engine.dispose()
