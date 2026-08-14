"""support structured extraction

Revision ID: 7af44def6f21
Revises: ed400f92bdfe
Create Date: 2026-08-14 16:11:27.220461
"""
from collections.abc import Sequence
from secrets import token_hex

from alembic import op
import sqlalchemy as sa


revision: str = '7af44def6f21'
down_revision: str | None = 'ed400f92bdfe'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite cannot add a UNIQUE constraint with ALTER TABLE. Add nullable
    # columns first, backfill upgrades that already contain data, and then use
    # Alembic batch mode so SQLite can recreate the tables safely.
    with op.batch_alter_table("alias_assertions") as batch_op:
        batch_op.add_column(sa.Column("alias_kind", sa.String(length=32), nullable=True))
    with op.batch_alter_table("expression_observations") as batch_op:
        batch_op.add_column(sa.Column("fingerprint", sa.String(length=64), nullable=True))

    op.execute("UPDATE alias_assertions SET alias_kind = 'nickname' WHERE alias_kind IS NULL")
    observations = sa.table(
        "expression_observations",
        sa.column("id", sa.Uuid()),
        sa.column("fingerprint", sa.String(length=64)),
    )
    connection = op.get_bind()
    existing_ids = connection.execute(
        sa.select(observations.c.id).where(observations.c.fingerprint.is_(None))
    ).scalars()
    for observation_id in existing_ids:
        connection.execute(
            observations.update()
            .where(observations.c.id == observation_id)
            .values(fingerprint=token_hex(32))
        )

    with op.batch_alter_table("alias_assertions") as batch_op:
        batch_op.alter_column("alias_kind", existing_type=sa.String(length=32), nullable=False)
    with op.batch_alter_table("expression_observations") as batch_op:
        batch_op.alter_column("fingerprint", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_unique_constraint(
            "uq_expression_observations_fingerprint", ["fingerprint"]
        )


def downgrade() -> None:
    with op.batch_alter_table("expression_observations") as batch_op:
        batch_op.drop_constraint("uq_expression_observations_fingerprint", type_="unique")
        batch_op.drop_column("fingerprint")
    with op.batch_alter_table("alias_assertions") as batch_op:
        batch_op.drop_column("alias_kind")
