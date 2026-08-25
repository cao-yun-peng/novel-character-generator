"""add visual enrichment rejection audit

Revision ID: f64b3e8d0a21
Revises: e53a2d7c9f10
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f64b3e8d0a21"
down_revision: str | None = "e53a2d7c9f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visual_enrichment_rejections",
        sa.Column("enrichment_run_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_query_run_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_passage_id", sa.Uuid(), nullable=True),
        sa.Column("field_path", sa.String(length=255), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("requested_start", sa.Integer(), nullable=False),
        sa.Column("requested_end", sa.Integer(), nullable=False),
        sa.Column("repaired_start", sa.Integer(), nullable=True),
        sa.Column("repaired_end", sa.Integer(), nullable=True),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["enrichment_run_id"], ["pipeline_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_query_run_id"], ["retrieval_query_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["character_id"], ["characters.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_passage_id"], ["retrieval_passages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_visual_enrichment_rejections_enrichment_run_id"),
        "visual_enrichment_rejections",
        ["enrichment_run_id"],
    )
    op.create_index(
        op.f("ix_visual_enrichment_rejections_retrieval_query_run_id"),
        "visual_enrichment_rejections",
        ["retrieval_query_run_id"],
    )
    op.create_index(
        op.f("ix_visual_enrichment_rejections_character_id"),
        "visual_enrichment_rejections",
        ["character_id"],
    )
    op.create_index(
        op.f("ix_visual_enrichment_rejections_retrieval_passage_id"),
        "visual_enrichment_rejections",
        ["retrieval_passage_id"],
    )
    op.create_index(
        "ix_visual_rejections_run_created",
        "visual_enrichment_rejections",
        ["enrichment_run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_visual_rejections_run_created",
        table_name="visual_enrichment_rejections",
    )
    op.drop_index(
        op.f("ix_visual_enrichment_rejections_retrieval_passage_id"),
        table_name="visual_enrichment_rejections",
    )
    op.drop_index(
        op.f("ix_visual_enrichment_rejections_character_id"),
        table_name="visual_enrichment_rejections",
    )
    op.drop_index(
        op.f("ix_visual_enrichment_rejections_retrieval_query_run_id"),
        table_name="visual_enrichment_rejections",
    )
    op.drop_index(
        op.f("ix_visual_enrichment_rejections_enrichment_run_id"),
        table_name="visual_enrichment_rejections",
    )
    op.drop_table("visual_enrichment_rejections")
