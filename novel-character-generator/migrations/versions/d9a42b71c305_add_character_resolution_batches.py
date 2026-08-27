"""add model-driven character resolution batches

Revision ID: d9a42b71c305
Revises: bf21c2d4e6a8
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9a42b71c305"
down_revision: str | None = "bf21c2d4e6a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    naming_convention = {
        "uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s"
    }
    with op.batch_alter_table(
        "characters", naming_convention=naming_convention
    ) as batch_op:
        # A canonical display name is not an identity key. Distinct people in one
        # novel may legitimately share it; convergence groups by ids/creation_key.
        batch_op.drop_constraint(
            "uq_characters_novel_id_canonical_name", type_="unique"
        )

    op.create_table(
        "character_resolution_chunks",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_ordinal", sa.Integer(), nullable=False),
        sa.Column("extraction_result", sa.JSON(), nullable=False),
        sa.Column("candidate_packet", sa.JSON(), nullable=False),
        sa.Column("resolution_input_hash", sa.String(length=64), nullable=True),
        sa.Column("resolution_result", sa.JSON(), nullable=True),
        sa.Column("memory_after", sa.JSON(), nullable=True),
        sa.Column("resolver_version", sa.String(length=255), nullable=True),
        sa.Column("context_truncated", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "chunk_ordinal >= 0", name="ck_character_resolution_chunk_ordinal"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_chunk_id"], ["text_chunks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "source_chunk_id"),
        sa.UniqueConstraint("run_id", "chunk_ordinal"),
    )
    op.create_index(
        op.f("ix_character_resolution_chunks_run_id"),
        "character_resolution_chunks",
        ["run_id"],
    )
    op.create_index(
        op.f("ix_character_resolution_chunks_source_chunk_id"),
        "character_resolution_chunks",
        ["source_chunk_id"],
    )
    op.create_index(
        op.f("ix_character_resolution_chunks_status"),
        "character_resolution_chunks",
        ["status"],
    )

    op.create_table(
        "character_convergence_batches",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("batch_index", sa.Integer(), nullable=False),
        sa.Column("start_chunk_ordinal", sa.Integer(), nullable=False),
        sa.Column("end_chunk_ordinal", sa.Integer(), nullable=False),
        sa.Column("final_batch", sa.Boolean(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("memory_after", sa.JSON(), nullable=True),
        sa.Column("resolver_version", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "batch_index >= 0", name="ck_character_convergence_batch_index"
        ),
        sa.CheckConstraint(
            "end_chunk_ordinal >= start_chunk_ordinal",
            name="ck_character_convergence_chunk_range",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "batch_index"),
    )
    op.create_index(
        op.f("ix_character_convergence_batches_run_id"),
        "character_convergence_batches",
        ["run_id"],
    )
    op.create_index(
        op.f("ix_character_convergence_batches_status"),
        "character_convergence_batches",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("character_convergence_batches")
    op.drop_table("character_resolution_chunks")
    with op.batch_alter_table("characters") as batch_op:
        batch_op.create_unique_constraint(
            "uq_characters_novel_id_canonical_name",
            ["novel_id", "canonical_name"],
        )
