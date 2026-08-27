"""add R2 raw model response capture

Revision ID: f9a1e5c72d30
Revises: f2c6d8a91b40
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9a1e5c72d30"
down_revision: str | None = "f2c6d8a91b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_raw_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(sa.Column("resolver_raw_response", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("resolver_raw_message_content", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("resolver_raw_response_hash", sa.String(length=64), nullable=True)
        )


def _drop_raw_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_column("resolver_raw_response_hash")
        batch_op.drop_column("resolver_raw_message_content")
        batch_op.drop_column("resolver_raw_response")


def upgrade() -> None:
    _add_raw_columns("character_resolution_chunks")
    _add_raw_columns("character_convergence_batches")


def downgrade() -> None:
    _drop_raw_columns("character_convergence_batches")
    _drop_raw_columns("character_resolution_chunks")
