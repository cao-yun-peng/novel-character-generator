"""add retrieval index foundation

Revision ID: c31b9e84a6d2
Revises: b7e3c0a1d2f4
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c31b9e84a6d2"
down_revision: str | None = "b7e3c0a1d2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
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
    )


def upgrade() -> None:
    op.create_table(
        "retrieval_index_builds",
        sa.Column("source_document_version_id", sa.Uuid(), nullable=False),
        sa.Column("index_version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("pipeline_run_id", sa.Uuid(), nullable=True),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("passage_algorithm_version", sa.String(100), nullable=False),
        sa.Column("lexical_profile_version", sa.String(100), nullable=False),
        sa.Column("embedding_profile_version", sa.String(100), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["source_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_document_version_id", "index_version"),
        sa.UniqueConstraint("pipeline_run_id"),
    )
    op.create_index(
        "ix_retrieval_builds_source_status",
        "retrieval_index_builds",
        ["source_document_version_id", "status"],
    )
    op.create_index(
        op.f("ix_retrieval_index_builds_source_document_version_id"),
        "retrieval_index_builds",
        ["source_document_version_id"],
    )
    op.create_index(
        op.f("ix_retrieval_index_builds_status"),
        "retrieval_index_builds",
        ["status"],
    )

    op.create_table(
        "retrieval_passages",
        sa.Column("retrieval_index_build_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=True),
        sa.Column("chapter_ordinal", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("normalized_char_start", sa.Integer(), nullable=False),
        sa.Column("normalized_char_end", sa.Integer(), nullable=False),
        sa.Column("original_char_start", sa.Integer(), nullable=False),
        sa.Column("original_char_end", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("previous_passage_id", sa.Uuid(), nullable=True),
        sa.Column("next_passage_id", sa.Uuid(), nullable=True),
        sa.Column(
            "oversized_sentence", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("ordinal >= 0", name="ck_retrieval_passages_ordinal_nonnegative"),
        sa.CheckConstraint(
            "token_count > 0", name="ck_retrieval_passages_token_count_positive"
        ),
        sa.CheckConstraint(
            "normalized_char_end > normalized_char_start",
            name="ck_retrieval_passages_normalized_span",
        ),
        sa.CheckConstraint(
            "original_char_end > original_char_start",
            name="ck_retrieval_passages_original_span",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_index_build_id"], ["retrieval_index_builds.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["previous_passage_id"], ["retrieval_passages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["next_passage_id"], ["retrieval_passages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("retrieval_index_build_id", "ordinal"),
    )
    op.create_index(
        op.f("ix_retrieval_passages_retrieval_index_build_id"),
        "retrieval_passages",
        ["retrieval_index_build_id"],
    )

    op.create_table(
        "retrieval_passage_chunk_spans",
        sa.Column("retrieval_passage_id", sa.Uuid(), nullable=False),
        sa.Column("source_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("passage_char_start", sa.Integer(), nullable=False),
        sa.Column("passage_char_end", sa.Integer(), nullable=False),
        sa.Column("chunk_char_start", sa.Integer(), nullable=False),
        sa.Column("chunk_char_end", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("passage_char_end > passage_char_start", name="ck_passage_chunk_span"),
        sa.CheckConstraint(
            "chunk_char_end > chunk_char_start", name="ck_passage_chunk_source_span"
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_passage_id"], ["retrieval_passages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["text_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("retrieval_passage_id", "source_chunk_id"),
    )
    op.create_index(
        op.f("ix_retrieval_passage_chunk_spans_retrieval_passage_id"),
        "retrieval_passage_chunk_spans",
        ["retrieval_passage_id"],
    )
    op.create_index(
        op.f("ix_retrieval_passage_chunk_spans_source_chunk_id"),
        "retrieval_passage_chunk_spans",
        ["source_chunk_id"],
    )

    op.create_table(
        "retrieval_passage_embeddings",
        sa.Column("retrieval_passage_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_profile_version", sa.String(100), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("qdrant_collection", sa.String(255), nullable=False),
        sa.Column("qdrant_point_id", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("dimension > 0", name="ck_retrieval_embedding_dimension_positive"),
        sa.ForeignKeyConstraint(
            ["retrieval_passage_id"], ["retrieval_passages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("retrieval_passage_id", "embedding_profile_version"),
    )
    op.create_index(
        op.f("ix_retrieval_passage_embeddings_retrieval_passage_id"),
        "retrieval_passage_embeddings",
        ["retrieval_passage_id"],
    )
    op.create_index(
        op.f("ix_retrieval_passage_embeddings_status"),
        "retrieval_passage_embeddings",
        ["status"],
    )

    op.create_table(
        "retrieval_query_runs",
        sa.Column("enrichment_run_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_index_build_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("life_phase_key", sa.String(100), nullable=True),
        sa.Column("field_groups", sa.JSON(), nullable=False),
        sa.Column("query_plan", sa.JSON(), nullable=False),
        sa.Column("query_plan_hash", sa.String(64), nullable=False),
        sa.Column("lexical_profile_version", sa.String(100), nullable=False),
        sa.Column("embedding_profile_version", sa.String(100), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["enrichment_run_id"], ["pipeline_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["retrieval_index_build_id"], ["retrieval_index_builds.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("enrichment_run_id", "query_plan_hash"),
    )
    for column in ("enrichment_run_id", "retrieval_index_build_id", "character_id"):
        op.create_index(op.f(f"ix_retrieval_query_runs_{column}"), "retrieval_query_runs", [column])

    op.create_table(
        "retrieval_query_hits",
        sa.Column("retrieval_query_run_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_passage_id", sa.Uuid(), nullable=False),
        sa.Column("source_channels", sa.JSON(), nullable=False),
        sa.Column("bm25_score", sa.Float(), nullable=True),
        sa.Column("vector_score", sa.Float(), nullable=True),
        sa.Column("bm25_rank", sa.Integer(), nullable=True),
        sa.Column("vector_rank", sa.Integer(), nullable=True),
        sa.Column("rrf_score", sa.Float(), nullable=False),
        sa.Column("expansion_reason", sa.String(100), nullable=True),
        sa.Column("final_rank", sa.Integer(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "final_rank > 0", name="ck_retrieval_query_hits_final_rank_positive"
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_query_run_id"], ["retrieval_query_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_passage_id"], ["retrieval_passages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("retrieval_query_run_id", "retrieval_passage_id"),
    )
    op.create_index(
        op.f("ix_retrieval_query_hits_retrieval_query_run_id"),
        "retrieval_query_hits",
        ["retrieval_query_run_id"],
    )
    op.create_index(
        op.f("ix_retrieval_query_hits_retrieval_passage_id"),
        "retrieval_query_hits",
        ["retrieval_passage_id"],
    )

    op.execute(
        "CREATE VIRTUAL TABLE retrieval_passages_fts USING fts5("
        "build_id UNINDEXED, passage_id UNINDEXED, body_terms, entity_terms, visual_terms, "
        "tokenize='unicode61')"
    )

    op.add_column("feature_observations", sa.Column("retrieval_passage_id", sa.Uuid()))
    with op.batch_alter_table("feature_observations") as batch_op:
        batch_op.create_foreign_key(
            "fk_feature_observations_retrieval_passage_id",
            "retrieval_passages",
            ["retrieval_passage_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        op.f("ix_feature_observations_retrieval_passage_id"),
        "feature_observations",
        ["retrieval_passage_id"],
    )

    op.add_column("feature_suggestions", sa.Column("source_document_version_id", sa.Uuid()))
    op.add_column("feature_suggestions", sa.Column("enrichment_run_id", sa.Uuid()))
    op.add_column("feature_suggestions", sa.Column("evidence_links", sa.JSON()))
    op.add_column("feature_suggestions", sa.Column("provenance_version", sa.String(100)))
    with op.batch_alter_table("feature_suggestions") as batch_op:
        batch_op.create_foreign_key(
            "fk_feature_suggestions_source_document_version_id",
            "source_document_versions",
            ["source_document_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_feature_suggestions_enrichment_run_id",
            "pipeline_runs",
            ["enrichment_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        op.f("ix_feature_suggestions_source_document_version_id"),
        "feature_suggestions",
        ["source_document_version_id"],
    )
    op.create_index(
        op.f("ix_feature_suggestions_enrichment_run_id"),
        "feature_suggestions",
        ["enrichment_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_feature_suggestions_enrichment_run_id"), table_name="feature_suggestions"
    )
    op.drop_index(
        op.f("ix_feature_suggestions_source_document_version_id"),
        table_name="feature_suggestions",
    )
    with op.batch_alter_table("feature_suggestions") as batch_op:
        batch_op.drop_constraint("fk_feature_suggestions_enrichment_run_id", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_feature_suggestions_source_document_version_id", type_="foreignkey"
        )
    op.drop_column("feature_suggestions", "provenance_version")
    op.drop_column("feature_suggestions", "evidence_links")
    op.drop_column("feature_suggestions", "enrichment_run_id")
    op.drop_column("feature_suggestions", "source_document_version_id")

    op.drop_index(
        op.f("ix_feature_observations_retrieval_passage_id"),
        table_name="feature_observations",
    )
    with op.batch_alter_table("feature_observations") as batch_op:
        batch_op.drop_constraint(
            "fk_feature_observations_retrieval_passage_id", type_="foreignkey"
        )
    op.drop_column("feature_observations", "retrieval_passage_id")

    op.execute("DROP TABLE retrieval_passages_fts")
    op.drop_table("retrieval_query_hits")
    op.drop_table("retrieval_query_runs")
    op.drop_table("retrieval_passage_embeddings")
    op.drop_table("retrieval_passage_chunk_spans")
    op.drop_table("retrieval_passages")
    op.drop_table("retrieval_index_builds")
