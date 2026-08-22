"""add character entity operations

Revision ID: a91c4e72d530
Revises: f6a2d07c19be
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a91c4e72d530"
down_revision: str | None = "f6a2d07c19be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("characters", sa.Column("merged_into_character_id", sa.Uuid(), nullable=True))
    with op.batch_alter_table("characters") as batch_op:
        batch_op.create_check_constraint("ck_characters_revision_positive", "revision >= 1")
        batch_op.create_foreign_key(
            "fk_characters_merged_into_character_id",
            "characters",
            ["merged_into_character_id"],
            ["id"],
        )
    op.create_index(
        op.f("ix_characters_merged_into_character_id"),
        "characters",
        ["merged_into_character_id"],
    )

    with op.batch_alter_table("decision_records") as batch_op:
        batch_op.alter_column("pipeline_run_id", existing_type=sa.Uuid(), nullable=True)
    with op.batch_alter_table("human_approvals") as batch_op:
        batch_op.alter_column("pipeline_step_id", existing_type=sa.Uuid(), nullable=True)

    op.create_table(
        "character_entity_operations",
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("source_character_ids", sa.JSON(), nullable=False),
        sa.Column("target_character_ids", sa.JSON(), nullable=False),
        sa.Column("action", sa.JSON(), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        op.f("ix_character_entity_operations_novel_id"),
        "character_entity_operations",
        ["novel_id"],
    )
    op.create_index(
        op.f("ix_character_entity_operations_status"),
        "character_entity_operations",
        ["status"],
    )
    op.create_index(
        "ix_character_entity_operations_novel_created",
        "character_entity_operations",
        ["novel_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_character_entity_operations_novel_created",
        table_name="character_entity_operations",
    )
    op.drop_index(
        op.f("ix_character_entity_operations_status"),
        table_name="character_entity_operations",
    )
    op.drop_index(
        op.f("ix_character_entity_operations_novel_id"),
        table_name="character_entity_operations",
    )
    op.drop_table("character_entity_operations")
    with op.batch_alter_table("human_approvals") as batch_op:
        batch_op.alter_column("pipeline_step_id", existing_type=sa.Uuid(), nullable=False)
    with op.batch_alter_table("decision_records") as batch_op:
        batch_op.alter_column("pipeline_run_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index(op.f("ix_characters_merged_into_character_id"), table_name="characters")
    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_constraint("fk_characters_merged_into_character_id", type_="foreignkey")
        batch_op.drop_constraint("ck_characters_revision_positive", type_="check")
    op.drop_column("characters", "merged_into_character_id")
    op.drop_column("characters", "revision")
