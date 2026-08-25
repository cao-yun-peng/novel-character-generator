"""persist character relations and reconcile kinship placeholders

Revision ID: d42f1c9a8b6e
Revises: c31b9e84a6d2
Create Date: 2026-08-25
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "d42f1c9a8b6e"
down_revision: str | None = "c31b9e84a6d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FAMILY_RELATIONS = {
    "family.father": ("father", "父亲"),
    "family.mother": ("mother", "母亲"),
    "family.parent": ("parent", "父母"),
    "family.son": ("son", "儿子"),
    "family.daughter": ("daughter", "女儿"),
    "family.child": ("child", "孩子"),
    "family.spouse": ("spouse", "配偶"),
    "family.husband": ("husband", "丈夫"),
    "family.wife": ("wife", "妻子"),
    "family.brother": ("brother", "兄弟"),
    "family.sister": ("sister", "姐妹"),
}


def _json_value(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _id_text(value: object) -> str:
    return str(value).replace("-", "").casefold()


def upgrade() -> None:
    op.create_table(
        "character_relations",
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("source_character_id", sa.Uuid(), nullable=False),
        sa.Column("target_character_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("source_document_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("grounding_status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("record_status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_character_relations_confidence",
        ),
        sa.CheckConstraint("char_end > char_start", name="ck_character_relations_span"),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_character_id"], ["characters.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_character_id"], ["characters.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["source_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["text_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index(
        op.f("ix_character_relations_novel_id"), "character_relations", ["novel_id"]
    )
    op.create_index(
        op.f("ix_character_relations_source_character_id"),
        "character_relations",
        ["source_character_id"],
    )
    op.create_index(
        op.f("ix_character_relations_target_character_id"),
        "character_relations",
        ["target_character_id"],
    )
    op.create_index(
        op.f("ix_character_relations_relation_type"),
        "character_relations",
        ["relation_type"],
    )
    op.create_index(
        op.f("ix_character_relations_source_document_version_id"),
        "character_relations",
        ["source_document_version_id"],
    )
    op.create_index(
        op.f("ix_character_relations_source_chunk_id"),
        "character_relations",
        ["source_chunk_id"],
    )
    op.create_index(
        "ix_character_relations_source_status",
        "character_relations",
        ["source_character_id", "record_status"],
    )
    op.create_index(
        "ix_character_relations_target_status",
        "character_relations",
        ["target_character_id", "record_status"],
    )
    _backfill_relations_and_placeholders()


def _backfill_relations_and_placeholders() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    characters = sa.Table("characters", metadata, autoload_with=bind)
    observations = sa.Table("feature_observations", metadata, autoload_with=bind)
    relations = sa.Table("character_relations", metadata, autoload_with=bind)
    mentions = sa.Table("mention_spans", metadata, autoload_with=bind)
    aliases = sa.Table("alias_assertions", metadata, autoload_with=bind)

    character_rows = list(bind.execute(sa.select(characters)))
    characters_by_key = {
        (_id_text(row.novel_id), row.canonical_name): row for row in character_rows
    }
    family_rows = list(
        bind.execute(
            sa.select(observations, characters.c.canonical_name, characters.c.novel_id)
            .join(characters, characters.c.id == observations.c.character_id)
            .where(
                observations.c.field_path.in_(tuple(_FAMILY_RELATIONS)),
                observations.c.record_status.in_(("active", "pending")),
            )
        )
    )
    now = datetime.now(UTC)
    placeholder_targets: dict[object, object] = {}

    for row in family_rows:
        target_name = _json_value(row.value)
        if not isinstance(target_name, str) or not target_name.strip():
            continue
        target = characters_by_key.get((_id_text(row.novel_id), target_name.strip()))
        relation = _FAMILY_RELATIONS.get(row.field_path)
        if target is None or relation is None:
            continue
        relation_type, label = relation
        if (
            row.source_chunk_id is not None
            and row.source_document_version_id is not None
            and row.extraction_run_id is not None
            and row.evidence_quote
            and row.char_start is not None
            and row.char_end is not None
            and row.char_end > row.char_start
        ):
            fingerprint = hashlib.sha256(
                f"family-observation:{row.id}:{relation_type}:{target.id}".encode()
            ).hexdigest()
            bind.execute(
                relations.insert().values(
                    id=str(uuid4()),
                    novel_id=row.novel_id,
                    source_character_id=row.character_id,
                    target_character_id=target.id,
                    relation_type=relation_type,
                    source_document_version_id=row.source_document_version_id,
                    source_chunk_id=row.source_chunk_id,
                    scene_id=row.scene_id,
                    evidence_quote=row.evidence_quote,
                    char_start=row.char_start,
                    char_end=row.char_end,
                    grounding_status=row.grounding_status,
                    confidence=row.confidence,
                    extraction_run_id=row.extraction_run_id,
                    extractor_version=row.extractor_version,
                    fingerprint=fingerprint,
                    record_status=row.record_status,
                    created_at=row.created_at,
                    updated_at=now,
                )
            )
        for placeholder_name in (
            f"{row.canonical_name}{label}",
            f"{row.canonical_name}的{label}",
        ):
            placeholder = characters_by_key.get((_id_text(row.novel_id), placeholder_name))
            if placeholder is not None and placeholder.id != target.id:
                placeholder_targets[placeholder.id] = target.id

    substantive_tables = [
        ("feature_observations", "character_id"),
        ("expression_observations", "character_id"),
        ("character_appearance_states", "character_id"),
        ("feature_suggestions", "character_id"),
    ]
    inspector = sa.inspect(bind)
    for placeholder_id, target_id in placeholder_targets.items():
        has_substantive_records = False
        for table_name, column_name in substantive_tables:
            if not inspector.has_table(table_name):
                continue
            substantive_table = sa.Table(
                table_name, sa.MetaData(), autoload_with=bind
            )
            count = bind.scalar(
                sa.select(sa.func.count())
                .select_from(substantive_table)
                .where(substantive_table.c[column_name] == placeholder_id)
            )
            if count:
                has_substantive_records = True
                break
        if has_substantive_records:
            continue
        mention_rows = list(
            bind.execute(
                sa.select(mentions.c.id, mentions.c.candidate_character_ids).where(
                    mentions.c.resolved_character_id == placeholder_id
                )
            )
        )
        bind.execute(
            mentions.update()
            .where(mentions.c.resolved_character_id == placeholder_id)
            .values(resolved_character_id=target_id, updated_at=now)
        )
        for mention in mention_rows:
            candidates = _json_value(mention.candidate_character_ids)
            if not isinstance(candidates, list):
                continue
            replacement = []
            for candidate in candidates:
                value = str(target_id) if _id_text(candidate) == _id_text(placeholder_id) else candidate
                if value not in replacement:
                    replacement.append(value)
            bind.execute(
                mentions.update()
                .where(mentions.c.id == mention.id)
                .values(candidate_character_ids=replacement, updated_at=now)
            )
        bind.execute(
            aliases.update()
            .where(aliases.c.proposed_character_id == placeholder_id)
            .values(proposed_character_id=target_id, updated_at=now)
        )
        bind.execute(
            aliases.update()
            .where(aliases.c.speaker_id == placeholder_id)
            .values(speaker_id=target_id, updated_at=now)
        )
        bind.execute(
            characters.update()
            .where(characters.c.id == placeholder_id)
            .values(
                status="merged",
                merged_into_character_id=target_id,
                revision=characters.c.revision + 1,
                updated_at=now,
            )
        )


def downgrade() -> None:
    op.drop_index("ix_character_relations_target_status", table_name="character_relations")
    op.drop_index("ix_character_relations_source_status", table_name="character_relations")
    op.drop_index(
        op.f("ix_character_relations_source_chunk_id"), table_name="character_relations"
    )
    op.drop_index(
        op.f("ix_character_relations_source_document_version_id"),
        table_name="character_relations",
    )
    op.drop_index(
        op.f("ix_character_relations_relation_type"), table_name="character_relations"
    )
    op.drop_index(
        op.f("ix_character_relations_target_character_id"),
        table_name="character_relations",
    )
    op.drop_index(
        op.f("ix_character_relations_source_character_id"),
        table_name="character_relations",
    )
    op.drop_index(op.f("ix_character_relations_novel_id"), table_name="character_relations")
    op.drop_table("character_relations")
