"""add character appearance resolution

Revision ID: f6a2d07c19be
Revises: e4b7281ca650
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a2d07c19be"
down_revision: str | None = "e4b7281ca650"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "character_appearance_states",
        sa.Column("state_kind", sa.String(length=32), server_default="base_age_stage", nullable=False),
    )
    op.add_column(
        "character_appearance_states",
        sa.Column("merge_priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "character_appearance_states",
        sa.Column(
            "resolver_version",
            sa.String(length=100),
            server_default="appearance-resolver-v1",
            nullable=False,
        ),
    )
    op.add_column(
        "character_appearance_states", sa.Column("created_by_run_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "character_appearance_states",
        sa.Column("record_status", sa.String(length=32), server_default="active", nullable=False),
    )
    with op.batch_alter_table("character_appearance_states") as batch_op:
        batch_op.create_foreign_key(
            "fk_appearance_states_created_by_run_id",
            "pipeline_runs",
            ["created_by_run_id"],
            ["id"],
        )
    op.create_index(
        op.f("ix_character_appearance_states_character_id"),
        "character_appearance_states",
        ["character_id"],
    )
    op.create_index(
        "ix_appearance_states_character_status",
        "character_appearance_states",
        ["character_id", "status", "record_status"],
    )

    op.add_column(
        "character_render_profiles", sa.Column("default_stage_key", sa.String(100), nullable=True)
    )
    op.add_column(
        "character_render_profiles",
        sa.Column("field_suggestions", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )

    op.create_table(
        "character_conflicts",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("field_path", sa.String(length=255), nullable=False),
        sa.Column("appearance_state_ids", sa.JSON(), nullable=False),
        sa.Column("candidate_values", sa.JSON(), nullable=False),
        sa.Column("temporal_scope", sa.JSON(), nullable=False),
        sa.Column("merge_priority", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("revision >= 1", name="ck_character_conflicts_revision_positive"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "fingerprint"),
    )
    op.create_index(
        op.f("ix_character_conflicts_character_id"), "character_conflicts", ["character_id"]
    )
    op.create_index(
        op.f("ix_character_conflicts_created_at"), "character_conflicts", ["created_at"]
    )
    op.create_index(
        "ix_character_conflicts_character_status",
        "character_conflicts",
        ["character_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_character_conflicts_character_status", table_name="character_conflicts")
    op.drop_index(op.f("ix_character_conflicts_created_at"), table_name="character_conflicts")
    op.drop_index(op.f("ix_character_conflicts_character_id"), table_name="character_conflicts")
    op.drop_table("character_conflicts")
    op.drop_column("character_render_profiles", "field_suggestions")
    op.drop_column("character_render_profiles", "default_stage_key")
    op.drop_index("ix_appearance_states_character_status", table_name="character_appearance_states")
    op.drop_index(
        op.f("ix_character_appearance_states_character_id"),
        table_name="character_appearance_states",
    )
    with op.batch_alter_table("character_appearance_states") as batch_op:
        batch_op.drop_constraint("fk_appearance_states_created_by_run_id", type_="foreignkey")
    op.drop_column("character_appearance_states", "record_status")
    op.drop_column("character_appearance_states", "created_by_run_id")
    op.drop_column("character_appearance_states", "resolver_version")
    op.drop_column("character_appearance_states", "merge_priority")
    op.drop_column("character_appearance_states", "state_kind")
