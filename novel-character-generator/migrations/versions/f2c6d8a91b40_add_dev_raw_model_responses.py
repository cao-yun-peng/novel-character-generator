"""add development-only raw model response capture

Revision ID: f2c6d8a91b40
Revises: a3e8c1d4f620
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c6d8a91b40"
down_revision: str | None = "a3e8c1d4f620"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("character_resolution_chunks") as batch_op:
        batch_op.add_column(sa.Column("provider_raw_response", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("provider_raw_message_content", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("provider_raw_response_hash", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("character_resolution_chunks") as batch_op:
        batch_op.drop_column("provider_raw_response_hash")
        batch_op.drop_column("provider_raw_message_content")
        batch_op.drop_column("provider_raw_response")
