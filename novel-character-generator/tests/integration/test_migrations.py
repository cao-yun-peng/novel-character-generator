from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

EXPECTED_TABLES = {
    "agent_evaluations",
    "agent_runs",
    "agent_turns",
    "alias_assertions",
    "artifacts",
    "chapters",
    "character_appearance_states",
    "character_image_sets",
    "character_render_profiles",
    "character_stage_images",
    "characters",
    "decision_records",
    "expression_observations",
    "external_operations",
    "feature_observations",
    "generated_images",
    "human_approvals",
    "mention_spans",
    "model_calls",
    "novels",
    "pipeline_runs",
    "pipeline_steps",
    "run_events",
    "scenes",
    "source_documents",
    "story_events",
    "text_chunks",
    "timelines",
    "tool_calls",
}


def test_initial_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    config = Config("alembic.ini")
    config.cmd_opts = type(
        "Options", (), {"x": [f"database_url=sqlite+aiosqlite:///{database_path}"]}
    )()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(f"sqlite:///{database_path}")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
