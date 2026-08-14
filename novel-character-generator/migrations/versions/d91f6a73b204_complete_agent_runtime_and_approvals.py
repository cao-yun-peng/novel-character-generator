"""complete agent runtime and approval persistence

Revision ID: d91f6a73b204
Revises: c8e1a9d42f30
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d91f6a73b204"
down_revision: str | None = "c8e1a9d42f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("attempt", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "agent_spec_snapshot", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "tool_spec_versions", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "prompt_version", sa.String(length=100), server_default="legacy", nullable=False
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("model_policy", sa.String(length=100), server_default="legacy", nullable=False),
    )
    op.add_column(
        "agent_runs",
        sa.Column("output_schema", sa.String(length=255), server_default="legacy", nullable=False),
    )
    op.add_column(
        "agent_runs",
        sa.Column("permission", sa.String(length=32), server_default="read", nullable=False),
    )
    op.add_column(
        "agent_runs", sa.Column("evaluation_version", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "agent_runs",
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "agent_runs",
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "total_cost",
            sa.Numeric(precision=18, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("latency_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )

    op.add_column(
        "human_approvals",
        sa.Column(
            "approval_type", sa.String(length=100), server_default="agent_tool", nullable=False
        ),
    )
    op.add_column(
        "human_approvals",
        sa.Column(
            "subject_type", sa.String(length=100), server_default="pipeline_step", nullable=False
        ),
    )
    op.add_column("human_approvals", sa.Column("subject_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE human_approvals SET subject_id = pipeline_step_id")
    with op.batch_alter_table("human_approvals") as batch_op:
        batch_op.alter_column("subject_id", existing_type=sa.Uuid(), nullable=False)
    op.add_column(
        "human_approvals",
        sa.Column("requested_by_agent_run_id", sa.Uuid(), nullable=True),
    )
    with op.batch_alter_table("human_approvals") as batch_op:
        batch_op.create_foreign_key(
            "fk_human_approvals_requested_by_agent_run_id",
            "agent_runs",
            ["requested_by_agent_run_id"],
            ["id"],
        )
    op.add_column(
        "human_approvals",
        sa.Column("lease_generation", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "human_approvals",
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "human_approvals", sa.Column("decision_payload_hash", sa.String(length=64), nullable=True)
    )
    op.create_index(
        op.f("ix_human_approvals_approval_type"),
        "human_approvals",
        ["approval_type"],
    )
    op.create_index(
        op.f("ix_human_approvals_subject_id"), "human_approvals", ["subject_id"]
    )
    op.create_index(
        "ix_human_approvals_queue",
        "human_approvals",
        ["status", "approval_type", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_human_approvals_queue", table_name="human_approvals")
    op.drop_index(op.f("ix_human_approvals_subject_id"), table_name="human_approvals")
    op.drop_index(op.f("ix_human_approvals_approval_type"), table_name="human_approvals")
    op.drop_column("human_approvals", "decision_payload_hash")
    op.drop_column("human_approvals", "revision")
    op.drop_column("human_approvals", "lease_generation")
    with op.batch_alter_table("human_approvals") as batch_op:
        batch_op.drop_constraint(
            "fk_human_approvals_requested_by_agent_run_id", type_="foreignkey"
        )
    op.drop_column("human_approvals", "requested_by_agent_run_id")
    op.drop_column("human_approvals", "subject_id")
    op.drop_column("human_approvals", "subject_type")
    op.drop_column("human_approvals", "approval_type")

    op.drop_column("agent_runs", "latency_ms")
    op.drop_column("agent_runs", "total_cost")
    op.drop_column("agent_runs", "output_tokens")
    op.drop_column("agent_runs", "input_tokens")
    op.drop_column("agent_runs", "completed_at")
    op.drop_column("agent_runs", "started_at")
    op.drop_column("agent_runs", "evaluation_version")
    op.drop_column("agent_runs", "permission")
    op.drop_column("agent_runs", "output_schema")
    op.drop_column("agent_runs", "model_policy")
    op.drop_column("agent_runs", "prompt_version")
    op.drop_column("agent_runs", "tool_spec_versions")
    op.drop_column("agent_runs", "agent_spec_snapshot")
    op.drop_column("agent_runs", "attempt")
