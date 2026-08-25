"""normalize phases, visual age semantics, and canonical timelines

Revision ID: e53a2d7c9f10
Revises: d42f1c9a8b6e
Create Date: 2026-08-25
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e53a2d7c9f10"
down_revision: str | None = "d42f1c9a8b6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PHASE_ALIASES = {
    "previous_life": "past_life",
    "前世": "past_life",
    "前世唐门": "past_life",
    "唐门前世": "past_life",
    "前一世": "past_life",
    "past_life": "past_life",
    "reincarnated_child": "reincarnated_childhood",
    "reincarnated_childhood": "reincarnated_childhood",
    "reincarnated childhood": "reincarnated_childhood",
    "转生幼年": "reincarnated_childhood",
    "转世幼年": "reincarnated_childhood",
    "转世童年": "reincarnated_childhood",
    "重生童年": "reincarnated_childhood",
    "childhood": "childhood",
    "童年": "childhood",
    "幼年": "childhood",
    "adolescence": "adolescence",
    "少年": "adolescence",
    "adulthood": "adulthood",
    "成年": "adulthood",
}
_PHASE_LABELS = {
    "past_life": "前世",
    "reincarnated_childhood": "转生幼年",
    "childhood": "幼年",
    "adolescence": "少年期",
    "adulthood": "成年期",
}
_AGE_STAGES = {
    "child": "childhood",
    "children": "childhood",
    "childhood": "childhood",
    "幼儿": "childhood",
    "幼年": "childhood",
    "儿童": "childhood",
    "童年": "childhood",
    "adolescent": "adolescence",
    "adolescence": "adolescence",
    "少年": "adolescence",
    "青少年": "adolescence",
    "adult": "adulthood",
    "adulthood": "adulthood",
    "young adult": "adulthood",
    "young_adult": "adulthood",
    "青年": "adulthood",
    "成年": "adulthood",
    "elderly": "elderly",
    "old age": "elderly",
    "老年": "elderly",
}
_FIELD_ALIASES = {
    "martial_soul": "abilities.martial_spirit",
    "martial_spirit": "abilities.martial_spirit",
    "spirit.name": "abilities.martial_spirit",
    "innate_soul_power": "abilities.innate_soul_power",
    "soul.innate_full_soul_power": "abilities.innate_soul_power",
    "soul_power.innate": "abilities.innate_soul_power",
    "soul_power.innate_full": "abilities.innate_soul_power",
    "soul.twin_martial_spirits": "abilities.twin_martial_spirits",
}
_EXPERIENCED_AGE_MARKERS = (
    "实际年龄",
    "两世为人",
    "成年人心态",
    "成人心态",
    "心理年龄",
    "心智年龄",
)
_MAIN_TIMELINE_NAMES = {
    "main",
    "main_timeline",
    "canonical",
    "canonical_timeline",
    "主线",
    "主时间线",
    "主线时间线",
}


def _json(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _phase(scope: object) -> object:
    decoded = _json(scope)
    if not isinstance(decoded, dict):
        return decoded
    result = dict(decoded)
    raw_key = result.get("life_phase_key")
    raw_label = result.get("life_phase_label")
    token = None
    if isinstance(raw_key, str) and raw_key.strip():
        token = raw_key.strip().casefold().replace("-", "_")
    elif isinstance(raw_label, str) and raw_label.strip():
        token = raw_label.strip().casefold().replace("-", "_")
    canonical = _PHASE_ALIASES.get(token or "")
    if canonical:
        result["life_phase_key"] = canonical
        result["life_phase_label"] = _PHASE_LABELS[canonical]
    return result


def _id_text(value: object) -> str:
    return str(value).replace("-", "").casefold()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    metadata = sa.MetaData()
    observations = sa.Table("feature_observations", metadata, autoload_with=bind)
    rows = list(
        bind.execute(
            sa.select(
                observations.c.id,
                observations.c.character_id,
                observations.c.field_path,
                observations.c.value,
                observations.c.evidence_quote,
                observations.c.temporal_scope,
            )
        )
    )
    normalized_rows: list[tuple[object, object, str, object, dict[str, object]]] = []
    reincarnation_characters: set[str] = set()
    for row in rows:
        field_path = _FIELD_ALIASES.get(row.field_path, row.field_path)
        value = _json(row.value)
        quote = row.evidence_quote or ""
        scope = _phase(row.temporal_scope)
        if not isinstance(scope, dict):
            scope = {}
        if field_path == "age" and any(
            marker in quote for marker in _EXPERIENCED_AGE_MARKERS
        ):
            field_path = "identity.experienced_age"
        elif field_path == "age_stage" and any(
            marker in quote for marker in _EXPERIENCED_AGE_MARKERS
        ):
            field_path = "identity.mental_age_stage"
        if field_path == "age_stage" and isinstance(value, str):
            value = _AGE_STAGES.get(value.strip().casefold(), value.strip())
        if field_path == "abilities.innate_soul_power" and value is True:
            value = "先天满魂力"
        if (
            field_path in {"identity.experienced_age", "identity.mental_age_stage"}
            and scope.get("life_phase_key") == "adulthood"
        ):
            scope.pop("life_phase_key", None)
            scope.pop("life_phase_label", None)
        if scope.get("life_phase_key") in {"past_life", "reincarnated_childhood"}:
            reincarnation_characters.add(_id_text(row.character_id))
        normalized_rows.append((row.id, row.character_id, field_path, value, scope))

    for row_id, character_id, field_path, value, scope in normalized_rows:
        if (
            _id_text(character_id) in reincarnation_characters
            and scope.get("life_phase_key") == "childhood"
        ):
            scope["life_phase_key"] = "reincarnated_childhood"
            scope["life_phase_label"] = _PHASE_LABELS["reincarnated_childhood"]
        bind.execute(
            observations.update()
            .where(observations.c.id == row_id)
            .values(
                field_path=field_path,
                value=value,
                temporal_scope=scope,
            )
        )

    for table_name in (
        "expression_observations",
        "character_appearance_states",
        "character_conflicts",
    ):
        if not inspector.has_table(table_name):
            continue
        table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
        scope_rows = list(bind.execute(sa.select(table.c.id, table.c.temporal_scope)))
        for row in scope_rows:
            bind.execute(
                table.update()
                .where(table.c.id == row.id)
                .values(temporal_scope=_phase(row.temporal_scope))
            )

    _merge_main_timeline_aliases(bind)


def _merge_main_timeline_aliases(bind: sa.Connection) -> None:
    timelines = sa.Table("timelines", sa.MetaData(), autoload_with=bind)
    timeline_rows = list(bind.execute(sa.select(timelines)))
    by_novel: dict[str, list[object]] = {}
    for row in timeline_rows:
        by_novel.setdefault(_id_text(row.novel_id), []).append(row)
    for rows in by_novel.values():
        canonical = next(
            (
                row
                for row in rows
                if row.canonicality == "canonical" and row.name == "主时间线"
            ),
            next((row for row in rows if row.canonicality == "canonical"), None),
        )
        if canonical is None:
            continue
        duplicates = [
            row
            for row in rows
            if row.id != canonical.id
            and row.name.strip().casefold().replace("-", "_").replace(" ", "_")
            in _MAIN_TIMELINE_NAMES
        ]
        for duplicate in duplicates:
            for table_name, column_name in (
                ("scenes", "timeline_id"),
                ("story_events", "timeline_id"),
                ("alias_assertions", "timeline_id"),
            ):
                table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
                bind.execute(
                    table.update()
                    .where(table.c[column_name] == duplicate.id)
                    .values({column_name: canonical.id})
                )
            bind.execute(
                timelines.update()
                .where(timelines.c.parent_timeline_id == duplicate.id)
                .values(parent_timeline_id=canonical.id)
            )
            for table_name in (
                "feature_observations",
                "expression_observations",
                "character_appearance_states",
                "character_conflicts",
            ):
                table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
                scope_rows = list(bind.execute(sa.select(table.c.id, table.c.temporal_scope)))
                for scope_row in scope_rows:
                    scope = _json(scope_row.temporal_scope)
                    if not isinstance(scope, dict):
                        continue
                    if _id_text(scope.get("timeline_id")) != _id_text(duplicate.id):
                        continue
                    scope = dict(scope)
                    scope["timeline_id"] = str(canonical.id)
                    bind.execute(
                        table.update()
                        .where(table.c.id == scope_row.id)
                        .values(temporal_scope=scope)
                    )
            bind.execute(timelines.delete().where(timelines.c.id == duplicate.id))


def downgrade() -> None:
    # Data canonicalization is intentionally monotonic; historical source facts remain auditable.
    pass
