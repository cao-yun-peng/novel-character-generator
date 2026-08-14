"""add versioned evaluation tables

Revision ID: c8e1a9d42f30
Revises: b21d91f4c8aa
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e1a9d42f30"
down_revision: str | None = "b21d91f4c8aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "eval_datasets",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("split_strategy", sa.JSON(), nullable=False),
        sa.Column("dataset_metadata", sa.JSON(), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version"),
    )
    op.create_index(op.f("ix_eval_datasets_created_at"), "eval_datasets", ["created_at"])
    op.create_index(op.f("ix_eval_datasets_frozen"), "eval_datasets", ["frozen"])

    op.create_table(
        "grader_versions",
        sa.Column("grader_key", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("grader_kind", sa.String(length=32), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("model_provider", sa.String(length=100), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("model_revision", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("rubric_version", sa.String(length=100), nullable=False),
        sa.Column("sampling_parameters", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grader_key", "version"),
        sa.UniqueConstraint("content_hash"),
    )
    op.create_index(op.f("ix_grader_versions_created_at"), "grader_versions", ["created_at"])

    op.create_table(
        "eval_cases",
        sa.Column("eval_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version", sa.String(length=100), nullable=False),
        sa.Column("source_novel_id", sa.Uuid(), nullable=True),
        sa.Column("source_document_version_id", sa.Uuid(), nullable=True),
        sa.Column("split_group_key", sa.String(length=255), nullable=False),
        sa.Column("split", sa.String(length=32), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("expected_output", sa.JSON(), nullable=False),
        sa.Column("evidence_spans", sa.JSON(), nullable=False),
        sa.Column("slice_tags", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("rubric_version", sa.String(length=100), nullable=False),
        sa.Column("annotation_status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["eval_dataset_id"], ["eval_datasets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_novel_id"], ["novels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["source_document_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_cases_created_at"), "eval_cases", ["created_at"])
    op.create_index(op.f("ix_eval_cases_split_group_key"), "eval_cases", ["split_group_key"])
    op.create_index(
        "ix_eval_cases_dataset_split_task",
        "eval_cases",
        ["eval_dataset_id", "split", "task_type"],
    )

    op.create_table(
        "eval_runs",
        sa.Column("eval_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version", sa.String(length=100), nullable=False),
        sa.Column("candidate_config_hash", sa.String(length=64), nullable=False),
        sa.Column("baseline_config_hash", sa.String(length=64), nullable=True),
        sa.Column("model_versions", sa.JSON(), nullable=False),
        sa.Column("prompt_versions", sa.JSON(), nullable=False),
        sa.Column("agent_spec_versions", sa.JSON(), nullable=False),
        sa.Column("tool_versions", sa.JSON(), nullable=False),
        sa.Column("schema_versions", sa.JSON(), nullable=False),
        sa.Column("workflow_profile_version", sa.String(length=100), nullable=True),
        sa.Column("grader_bundle_version", sa.String(length=100), nullable=False),
        sa.Column("random_seeds", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["eval_dataset_id"], ["eval_datasets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_runs_created_at"), "eval_runs", ["created_at"])
    op.create_index(op.f("ix_eval_runs_eval_dataset_id"), "eval_runs", ["eval_dataset_id"])
    op.create_index(op.f("ix_eval_runs_status"), "eval_runs", ["status"])

    op.create_table(
        "eval_results",
        sa.Column("eval_run_id", sa.Uuid(), nullable=False),
        sa.Column("eval_case_id", sa.Uuid(), nullable=False),
        sa.Column("grader_version_id", sa.Uuid(), nullable=False),
        sa.Column("raw_output_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("input_tokens >= 0", name="ck_eval_results_input_tokens_nonnegative"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_eval_results_latency_nonnegative"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_eval_results_output_tokens_nonnegative"),
        sa.ForeignKeyConstraint(["eval_case_id"], ["eval_cases.id"]),
        sa.ForeignKeyConstraint(
            ["eval_run_id"], ["eval_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["grader_version_id"], ["grader_versions.id"]),
        sa.ForeignKeyConstraint(["raw_output_artifact_id"], ["artifacts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eval_run_id", "eval_case_id", "grader_version_id"),
    )
    op.create_index(op.f("ix_eval_results_created_at"), "eval_results", ["created_at"])
    op.create_index(op.f("ix_eval_results_eval_case_id"), "eval_results", ["eval_case_id"])
    op.create_index(op.f("ix_eval_results_eval_run_id"), "eval_results", ["eval_run_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_eval_results_eval_run_id"), table_name="eval_results")
    op.drop_index(op.f("ix_eval_results_eval_case_id"), table_name="eval_results")
    op.drop_index(op.f("ix_eval_results_created_at"), table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_index(op.f("ix_eval_runs_status"), table_name="eval_runs")
    op.drop_index(op.f("ix_eval_runs_eval_dataset_id"), table_name="eval_runs")
    op.drop_index(op.f("ix_eval_runs_created_at"), table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_index("ix_eval_cases_dataset_split_task", table_name="eval_cases")
    op.drop_index(op.f("ix_eval_cases_split_group_key"), table_name="eval_cases")
    op.drop_index(op.f("ix_eval_cases_created_at"), table_name="eval_cases")
    op.drop_table("eval_cases")
    op.drop_index(op.f("ix_grader_versions_created_at"), table_name="grader_versions")
    op.drop_table("grader_versions")
    op.drop_index(op.f("ix_eval_datasets_frozen"), table_name="eval_datasets")
    op.drop_index(op.f("ix_eval_datasets_created_at"), table_name="eval_datasets")
    op.drop_table("eval_datasets")
