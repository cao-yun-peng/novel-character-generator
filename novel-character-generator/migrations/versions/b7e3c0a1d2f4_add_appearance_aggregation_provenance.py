"""add appearance aggregation provenance

Revision ID: b7e3c0a1d2f4
Revises: a91c4e72d530
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e3c0a1d2f4"
down_revision: str | None = "a91c4e72d530"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "character_conflicts",
        sa.Column(
            "conflict_kind",
            sa.String(length=32),
            server_default="incompatible_values",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_character_conflicts_conflict_kind"),
        "character_conflicts",
        ["conflict_kind"],
    )

    op.add_column(
        "character_appearance_states",
        sa.Column("aggregation_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_character_appearance_states_aggregation_fingerprint"),
        "character_appearance_states",
        ["aggregation_fingerprint"],
        unique=True,
    )

    op.add_column(
        "character_render_profiles",
        sa.Column("input_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "character_render_profiles",
        sa.Column(
            "record_status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
    )
    op.add_column(
        "character_render_profiles",
        sa.Column("source_document_version_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "character_render_profiles",
        sa.Column("aggregation_run_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "character_render_profiles",
        sa.Column("aggregation_metadata", sa.JSON(), nullable=True),
    )
    op.create_index(
        op.f("ix_character_render_profiles_input_fingerprint"),
        "character_render_profiles",
        ["input_fingerprint"],
    )
    op.create_index(
        op.f("ix_character_render_profiles_record_status"),
        "character_render_profiles",
        ["record_status"],
    )
    op.create_index(
        op.f("ix_character_render_profiles_source_document_version_id"),
        "character_render_profiles",
        ["source_document_version_id"],
    )
    op.create_index(
        op.f("ix_character_render_profiles_aggregation_run_id"),
        "character_render_profiles",
        ["aggregation_run_id"],
    )
    with op.batch_alter_table("character_render_profiles") as batch_op:
        batch_op.create_foreign_key(
            "fk_render_profiles_source_document_version_id",
            "source_document_versions",
            ["source_document_version_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_render_profiles_aggregation_run_id",
            "pipeline_runs",
            ["aggregation_run_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("character_render_profiles") as batch_op:
        batch_op.drop_constraint(
            "fk_render_profiles_aggregation_run_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_render_profiles_source_document_version_id", type_="foreignkey"
        )
    op.drop_index(
        op.f("ix_character_render_profiles_aggregation_run_id"),
        table_name="character_render_profiles",
    )
    op.drop_index(
        op.f("ix_character_render_profiles_source_document_version_id"),
        table_name="character_render_profiles",
    )
    op.drop_index(
        op.f("ix_character_render_profiles_input_fingerprint"),
        table_name="character_render_profiles",
    )
    op.drop_index(
        op.f("ix_character_render_profiles_record_status"),
        table_name="character_render_profiles",
    )
    op.drop_column("character_render_profiles", "aggregation_metadata")
    op.drop_column("character_render_profiles", "aggregation_run_id")
    op.drop_column("character_render_profiles", "source_document_version_id")
    op.drop_column("character_render_profiles", "input_fingerprint")
    op.drop_column("character_render_profiles", "record_status")
    op.drop_index(
        op.f("ix_character_appearance_states_aggregation_fingerprint"),
        table_name="character_appearance_states",
    )
    op.drop_column("character_appearance_states", "aggregation_fingerprint")
    op.drop_index(
        op.f("ix_character_conflicts_conflict_kind"),
        table_name="character_conflicts",
    )
    op.drop_column("character_conflicts", "conflict_kind")
