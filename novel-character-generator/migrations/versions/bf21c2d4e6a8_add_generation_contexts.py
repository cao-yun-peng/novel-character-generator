"""add immutable image generation contexts

Revision ID: bf21c2d4e6a8
Revises: a75c4f9e2b13
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bf21c2d4e6a8"
down_revision: str | None = "a75c4f9e2b13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_contexts",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("render_profile_id", sa.Uuid(), nullable=False),
        sa.Column("render_profile_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("workflow_profile", sa.String(length=100), nullable=False),
        sa.Column("workflow_version", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("target", sa.JSON(), nullable=False),
        sa.Column("context_payload", sa.JSON(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "candidate_count >= 1", name="ck_generation_context_candidate_count"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["character_id"], ["characters.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["render_profile_id"], ["character_render_profiles.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    for column in (
        "run_id",
        "character_id",
        "render_profile_id",
        "snapshot_hash",
        "context_hash",
        "status",
    ):
        op.create_index(
            op.f(f"ix_generation_contexts_{column}"),
            "generation_contexts",
            [column],
        )


def downgrade() -> None:
    op.drop_table("generation_contexts")
