"""version source documents and normalization maps

Revision ID: b21d91f4c8aa
Revises: 7af44def6f21
Create Date: 2026-08-14
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "b21d91f4c8aa"
down_revision: str | None = "7af44def6f21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_document_versions",
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("encoding", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("normalization_map_id", sa.Uuid(), nullable=True),
        sa.Column("supersedes_version_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["source_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_version_id"], ["source_document_versions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_document_id", "version"),
    )
    op.create_index(
        "ix_source_document_versions_document",
        "source_document_versions",
        ["source_document_id"],
    )
    op.create_index(
        "ix_source_document_versions_hash",
        "source_document_versions",
        ["content_sha256"],
    )
    op.create_index(
        "ix_source_document_versions_normalization_map",
        "source_document_versions",
        ["normalization_map_id"],
    )
    op.create_index(
        "ix_source_document_versions_created_at",
        "source_document_versions",
        ["created_at"],
    )

    op.create_table(
        "normalization_maps",
        sa.Column("source_document_version_id", sa.Uuid(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("original_boundaries", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["source_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_document_version_id"),
    )
    op.create_index(
        "ix_normalization_maps_created_at", "normalization_maps", ["created_at"]
    )

    op.add_column("source_documents", sa.Column("current_version_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_source_documents_current_version_id",
        "source_documents",
        ["current_version_id"],
    )

    connection = op.get_bind()
    source_documents = sa.table(
        "source_documents",
        sa.column("id", sa.Uuid()),
        sa.column("version", sa.String()),
        sa.column("sha256", sa.String()),
        sa.column("encoding", sa.String()),
        sa.column("mime_type", sa.String()),
        sa.column("storage_uri", sa.Text()),
        sa.column("byte_size", sa.Integer()),
        sa.column("normalization_map_version", sa.String()),
        sa.column("normalization_map", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("current_version_id", sa.Uuid()),
    )
    versions = sa.table(
        "source_document_versions",
        sa.column("id", sa.Uuid()),
        sa.column("source_document_id", sa.Uuid()),
        sa.column("version", sa.Integer()),
        sa.column("content_sha256", sa.String()),
        sa.column("encoding", sa.String()),
        sa.column("mime_type", sa.String()),
        sa.column("storage_uri", sa.Text()),
        sa.column("byte_size", sa.Integer()),
        sa.column("normalization_map_id", sa.Uuid()),
        sa.column("supersedes_version_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    maps = sa.table(
        "normalization_maps",
        sa.column("id", sa.Uuid()),
        sa.column("source_document_version_id", sa.Uuid()),
        sa.column("algorithm_version", sa.String()),
        sa.column("original_boundaries", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    for row in connection.execute(sa.select(source_documents)).mappings():
        version_id = uuid4()
        raw_map = row["normalization_map"] or {}
        boundaries = raw_map.get("original_boundaries")
        map_id = uuid4() if boundaries is not None else None
        connection.execute(
            versions.insert().values(
                id=version_id,
                source_document_id=row["id"],
                version=1,
                content_sha256=row["sha256"],
                encoding=row["encoding"],
                mime_type=row["mime_type"],
                storage_uri=row["storage_uri"],
                byte_size=row["byte_size"],
                normalization_map_id=map_id,
                supersedes_version_id=None,
                created_at=row["created_at"] or now,
                updated_at=row["updated_at"] or now,
            )
        )
        if map_id is not None:
            connection.execute(
                maps.insert().values(
                    id=map_id,
                    source_document_version_id=version_id,
                    algorithm_version=row["normalization_map_version"] or "legacy-v1",
                    original_boundaries=boundaries,
                    created_at=now,
                    updated_at=now,
                )
            )
        connection.execute(
            source_documents.update()
            .where(source_documents.c.id == row["id"])
            .values(current_version_id=version_id)
        )

    for table_name in ("chapters", "text_chunks"):
        op.add_column(
            table_name,
            sa.Column("source_document_version_id", sa.Uuid(), nullable=True),
        )
        op.create_index(
            f"ix_{table_name}_source_document_version_id",
            table_name,
            ["source_document_version_id"],
        )
        connection.execute(
            sa.text(
                f"UPDATE {table_name} SET source_document_version_id = "
                "(SELECT current_version_id FROM source_documents "
                f"WHERE source_documents.id = {table_name}.source_document_id)"
            )
        )

    naming_convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table(
        "chapters", naming_convention=naming_convention
    ) as batch_op:
        batch_op.drop_constraint("uq_chapters_novel_id", type_="unique")
        batch_op.create_unique_constraint(
            "uq_chapters_source_document_version_id_ordinal",
            ["source_document_version_id", "ordinal"],
        )
    with op.batch_alter_table(
        "text_chunks", naming_convention=naming_convention
    ) as batch_op:
        batch_op.drop_constraint("uq_text_chunks_novel_id", type_="unique")

    op.create_index(
        "ux_text_chunks_version_ordinal_hash",
        "text_chunks",
        ["source_document_version_id", "ordinal", "content_hash"],
        unique=True,
    )

    op.add_column(
        "mention_spans",
        sa.Column("source_document_version_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_mention_spans_source_document_version_id",
        "mention_spans",
        ["source_document_version_id"],
    )
    connection.execute(
        sa.text(
            "UPDATE mention_spans SET source_document_version_id = "
            "(SELECT source_document_version_id FROM text_chunks "
            "WHERE text_chunks.id = mention_spans.source_chunk_id)"
        )
    )

    op.add_column(
        "feature_observations",
        sa.Column("source_document_version_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "feature_observations", sa.Column("mention_span_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "feature_observations", sa.Column("manual_approval_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "feature_observations",
        sa.Column("record_status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.add_column(
        "feature_observations",
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "feature_observations", sa.Column("invalidated_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "feature_observations",
        sa.Column("invalidated_by_run_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_feature_observations_source_document_version_id",
        "feature_observations",
        ["source_document_version_id"],
    )
    connection.execute(
        sa.text(
            "UPDATE feature_observations SET "
            "source_document_version_id = (SELECT source_document_version_id FROM text_chunks "
            "WHERE text_chunks.id = feature_observations.source_chunk_id), "
            "recorded_at = created_at"
        )
    )

    op.add_column(
        "expression_observations",
        sa.Column("source_document_version_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_expression_observations_source_document_version_id",
        "expression_observations",
        ["source_document_version_id"],
    )
    connection.execute(
        sa.text(
            "UPDATE expression_observations SET source_document_version_id = "
            "(SELECT source_document_version_id FROM text_chunks "
            "WHERE text_chunks.id = expression_observations.source_chunk_id)"
        )
    )

    op.create_table(
        "event_participants",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("evidence_observation_ids", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["story_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "character_id", "role"),
    )
    op.create_index("ix_event_participants_event_id", "event_participants", ["event_id"])
    op.create_index(
        "ix_event_participants_character_id", "event_participants", ["character_id"]
    )
    op.create_index(
        "ix_event_participants_created_at", "event_participants", ["created_at"]
    )

    op.create_table(
        "feature_suggestions",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("field_path", sa.String(length=255), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("suggestion_kind", sa.String(length=32), nullable=False),
        sa.Column("resource_version", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("allowed_fields", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["human_approvals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_feature_suggestions_character_id", "feature_suggestions", ["character_id"]
    )
    op.create_index("ix_feature_suggestions_status", "feature_suggestions", ["status"])
    op.create_index(
        "ix_feature_suggestions_created_at", "feature_suggestions", ["created_at"]
    )

    op.add_column("external_operations", sa.Column("run_id", sa.Uuid(), nullable=True))
    op.add_column(
        "external_operations",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "external_operations",
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "external_operations",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "external_operations",
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_external_operations_run_id", "external_operations", ["run_id"])
    connection.execute(
        sa.text(
            "UPDATE external_operations SET "
            "run_id = (SELECT run_id FROM pipeline_steps "
            "WHERE pipeline_steps.id = external_operations.pipeline_step_id), "
            "request_fingerprint = request_hash"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_external_operations_run_id", table_name="external_operations")
    for column_name in (
        "last_reconciled_at",
        "attempt",
        "lease_generation",
        "request_fingerprint",
        "run_id",
    ):
        op.drop_column("external_operations", column_name)
    op.drop_index("ix_feature_suggestions_created_at", table_name="feature_suggestions")
    op.drop_index("ix_feature_suggestions_status", table_name="feature_suggestions")
    op.drop_index("ix_feature_suggestions_character_id", table_name="feature_suggestions")
    op.drop_table("feature_suggestions")
    op.drop_index("ix_event_participants_created_at", table_name="event_participants")
    op.drop_index("ix_event_participants_character_id", table_name="event_participants")
    op.drop_index("ix_event_participants_event_id", table_name="event_participants")
    op.drop_table("event_participants")
    op.drop_index(
        "ix_expression_observations_source_document_version_id",
        table_name="expression_observations",
    )
    op.drop_column("expression_observations", "source_document_version_id")

    op.drop_index(
        "ix_feature_observations_source_document_version_id",
        table_name="feature_observations",
    )
    for column_name in (
        "invalidated_by_run_id",
        "invalidated_at",
        "recorded_at",
        "record_status",
        "manual_approval_id",
        "mention_span_id",
        "source_document_version_id",
    ):
        op.drop_column("feature_observations", column_name)

    op.drop_index(
        "ix_mention_spans_source_document_version_id", table_name="mention_spans"
    )
    op.drop_column("mention_spans", "source_document_version_id")
    op.drop_index("ux_text_chunks_version_ordinal_hash", table_name="text_chunks")
    naming_convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table(
        "text_chunks", naming_convention=naming_convention
    ) as batch_op:
        batch_op.create_unique_constraint(
            "uq_text_chunks_novel_id_ordinal_content_hash",
            ["novel_id", "ordinal", "content_hash"],
        )
    with op.batch_alter_table(
        "chapters", naming_convention=naming_convention
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_chapters_source_document_version_id_ordinal", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_chapters_novel_id_ordinal", ["novel_id", "ordinal"]
        )
    for table_name in ("text_chunks", "chapters"):
        op.drop_index(
            f"ix_{table_name}_source_document_version_id", table_name=table_name
        )
        op.drop_column(table_name, "source_document_version_id")

    op.drop_index("ix_source_documents_current_version_id", table_name="source_documents")
    op.drop_column("source_documents", "current_version_id")
    op.drop_index("ix_normalization_maps_created_at", table_name="normalization_maps")
    op.drop_table("normalization_maps")
    op.drop_index(
        "ix_source_document_versions_created_at", table_name="source_document_versions"
    )
    op.drop_index(
        "ix_source_document_versions_normalization_map",
        table_name="source_document_versions",
    )
    op.drop_index("ix_source_document_versions_hash", table_name="source_document_versions")
    op.drop_index(
        "ix_source_document_versions_document", table_name="source_document_versions"
    )
    op.drop_table("source_document_versions")
