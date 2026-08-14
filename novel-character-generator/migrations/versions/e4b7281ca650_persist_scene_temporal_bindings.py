"""persist scene temporal bindings

Revision ID: e4b7281ca650
Revises: d91f6a73b204
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4b7281ca650"
down_revision: str | None = "d91f6a73b204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("label", sa.String(length=500), nullable=True))
    op.add_column("scenes", sa.Column("source_document_version_id", sa.Uuid(), nullable=True))
    op.add_column("scenes", sa.Column("source_chunk_id", sa.Uuid(), nullable=True))
    op.add_column("scenes", sa.Column("char_start", sa.Integer(), nullable=True))
    op.add_column("scenes", sa.Column("char_end", sa.Integer(), nullable=True))
    op.add_column(
        "scenes",
        sa.Column(
            "presentation_mode", sa.String(length=32), server_default="direct", nullable=False
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "reality_status", sa.String(length=32), server_default="canonical", nullable=False
        ),
    )
    op.add_column("scenes", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(
        "scenes",
        sa.Column(
            "binding_status", sa.String(length=32), server_default="hypothesis", nullable=False
        ),
    )
    op.add_column(
        "scenes",
        sa.Column("binding_revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("scenes", sa.Column("created_by_run_id", sa.Uuid(), nullable=True))
    op.add_column(
        "scenes",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    with op.batch_alter_table("scenes") as batch_op:
        batch_op.create_foreign_key(
            "fk_scenes_source_document_version_id",
            "source_document_versions",
            ["source_document_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_scenes_source_chunk_id",
            "text_chunks",
            ["source_chunk_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_scenes_created_by_run_id",
            "pipeline_runs",
            ["created_by_run_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_scenes_binding_revision_positive", "binding_revision >= 1"
        )
        batch_op.create_unique_constraint(
            "uq_scenes_source_span", ["source_chunk_id", "char_start", "char_end"]
        )
    op.create_index(
        op.f("ix_scenes_source_document_version_id"),
        "scenes",
        ["source_document_version_id"],
    )
    op.create_index(op.f("ix_scenes_source_chunk_id"), "scenes", ["source_chunk_id"])
    op.create_index(op.f("ix_scenes_binding_status"), "scenes", ["binding_status"])
    op.create_index(op.f("ix_scenes_created_at"), "scenes", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_scenes_created_at"), table_name="scenes")
    op.drop_index(op.f("ix_scenes_binding_status"), table_name="scenes")
    op.drop_index(op.f("ix_scenes_source_chunk_id"), table_name="scenes")
    op.drop_index(op.f("ix_scenes_source_document_version_id"), table_name="scenes")
    with op.batch_alter_table("scenes") as batch_op:
        batch_op.drop_constraint("uq_scenes_source_span", type_="unique")
        batch_op.drop_constraint("ck_scenes_binding_revision_positive", type_="check")
        batch_op.drop_constraint("fk_scenes_created_by_run_id", type_="foreignkey")
        batch_op.drop_constraint("fk_scenes_source_chunk_id", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_scenes_source_document_version_id", type_="foreignkey"
        )
    op.drop_column("scenes", "updated_at")
    op.drop_column("scenes", "created_at")
    op.drop_column("scenes", "created_by_run_id")
    op.drop_column("scenes", "binding_revision")
    op.drop_column("scenes", "binding_status")
    op.drop_column("scenes", "confidence")
    op.drop_column("scenes", "reality_status")
    op.drop_column("scenes", "presentation_mode")
    op.drop_column("scenes", "char_end")
    op.drop_column("scenes", "char_start")
    op.drop_column("scenes", "source_chunk_id")
    op.drop_column("scenes", "source_document_version_id")
    op.drop_column("scenes", "label")
