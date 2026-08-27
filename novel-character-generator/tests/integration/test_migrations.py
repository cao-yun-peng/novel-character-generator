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
    "character_conflicts",
    "character_entity_operations",
    "character_resolution_chunks",
    "character_convergence_batches",
    "character_image_sets",
    "character_render_profiles",
    "character_stage_images",
    "characters",
    "decision_records",
    "eval_cases",
    "eval_datasets",
    "eval_results",
    "eval_runs",
    "expression_observations",
    "event_participants",
    "external_operations",
    "feature_observations",
    "feature_suggestions",
    "generated_images",
    "generation_contexts",
    "grader_versions",
    "human_approvals",
    "mention_spans",
    "model_calls",
    "novels",
    "normalization_maps",
    "pipeline_runs",
    "pipeline_steps",
    "retrieval_index_builds",
    "retrieval_passage_chunk_spans",
    "retrieval_passage_embeddings",
    "retrieval_passages",
    "retrieval_passages_fts",
    "retrieval_query_hits",
    "retrieval_query_runs",
    "run_events",
    "scenes",
    "source_documents",
    "source_document_versions",
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
    inspector = inspect(engine)
    assert EXPECTED_TABLES <= set(inspector.get_table_names())
    resolution_columns = {
        column["name"] for column in inspector.get_columns("character_resolution_chunks")
    }
    assert {
        "provider_raw_response",
        "provider_raw_message_content",
        "provider_raw_response_hash",
        "resolver_raw_response",
        "resolver_raw_message_content",
        "resolver_raw_response_hash",
    } <= resolution_columns
    convergence_columns = {
        column["name"] for column in inspector.get_columns("character_convergence_batches")
    }
    assert {
        "resolver_raw_response",
        "resolver_raw_message_content",
        "resolver_raw_response_hash",
    } <= convergence_columns
    assert not any(
        set(item["column_names"]) == {"novel_id", "canonical_name"}
        for item in inspector.get_unique_constraints("characters")
    )
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(f"sqlite:///{database_path}")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
