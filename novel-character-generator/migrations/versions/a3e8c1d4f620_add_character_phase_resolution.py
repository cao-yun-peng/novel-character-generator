"""add grounded temporal signals and character phase resolution

Revision ID: a3e8c1d4f620
Revises: d9a42b71c305
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3e8c1d4f620"
down_revision: str | None = "d9a42b71c305"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "temporal_signals",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("mention_span_id", sa.Uuid(), nullable=True),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("feature_observation_ids", sa.JSON(), nullable=False),
        sa.Column("signal_id", sa.String(length=256), nullable=False),
        sa.Column("fact_candidate_key", sa.String(length=256), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("grounding_status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("resolution_status", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("char_end > char_start", name="ck_temporal_signals_span"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_temporal_signals_confidence",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["source_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["text_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mention_span_id"], ["mention_spans.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index(
        "ix_temporal_signals_character_status",
        "temporal_signals",
        ["character_id", "resolution_status"],
    )
    for column in (
        "run_id",
        "source_document_version_id",
        "source_chunk_id",
        "character_id",
        "kind",
        "resolution_status",
        "created_at",
    ):
        op.create_index(op.f(f"ix_temporal_signals_{column}"), "temporal_signals", [column])

    op.create_table(
        "character_life_phases",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_version_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("timeline_id", sa.Uuid(), nullable=False),
        sa.Column("phase_key", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("phase_order", sa.Numeric(20, 8), nullable=True),
        sa.Column("age_stage", sa.String(length=100), nullable=True),
        sa.Column("start_event_id", sa.Uuid(), nullable=True),
        sa.Column("end_event_id", sa.Uuid(), nullable=True),
        sa.Column("start_chapter_ordinal", sa.Integer(), nullable=True),
        sa.Column("end_chapter_ordinal", sa.Integer(), nullable=True),
        sa.Column("evidence_signal_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resolver_version", sa.String(length=100), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("record_status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_character_life_phases_revision"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_character_life_phases_confidence",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["source_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["start_event_id"], ["story_events.id"]),
        sa.ForeignKeyConstraint(["end_event_id"], ["story_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index(
        "ix_character_life_phases_character_status",
        "character_life_phases",
        ["character_id", "status", "record_status"],
    )
    for column in (
        "run_id",
        "source_document_version_id",
        "character_id",
        "timeline_id",
        "status",
        "input_fingerprint",
        "record_status",
        "created_at",
    ):
        op.create_index(
            op.f(f"ix_character_life_phases_{column}"),
            "character_life_phases",
            [column],
        )

    op.create_table(
        "observation_scope_bindings",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("phase_id", sa.Uuid(), nullable=True),
        sa.Column("timeline_id", sa.Uuid(), nullable=False),
        sa.Column("temporal_scope", sa.JSON(), nullable=False),
        sa.Column("presentation_mode", sa.String(length=32), nullable=False),
        sa.Column("reality_status", sa.String(length=32), nullable=False),
        sa.Column("transformation_state", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("resolver_version", sa.String(length=100), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("record_status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_observation_scope_bindings_revision"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_observation_scope_bindings_confidence",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["feature_observations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["phase_id"], ["character_life_phases.id"]),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index(
        "ix_observation_scope_bindings_observation_status",
        "observation_scope_bindings",
        ["observation_id", "status", "record_status"],
    )
    for column in (
        "run_id",
        "observation_id",
        "timeline_id",
        "status",
        "input_fingerprint",
        "record_status",
        "created_at",
    ):
        op.create_index(
            op.f(f"ix_observation_scope_bindings_{column}"),
            "observation_scope_bindings",
            [column],
        )

    op.create_table(
        "character_phase_resolutions",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_version_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("resolver_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["source_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "character_id"),
    )
    for column in (
        "run_id",
        "source_document_version_id",
        "character_id",
        "status",
        "created_at",
    ):
        op.create_index(
            op.f(f"ix_character_phase_resolutions_{column}"),
            "character_phase_resolutions",
            [column],
        )


def downgrade() -> None:
    op.drop_table("character_phase_resolutions")
    op.drop_table("observation_scope_bindings")
    op.drop_table("character_life_phases")
    op.drop_table("temporal_signals")
