"""persist provider result references for sync and async image jobs

Revision ID: c4b8a7d219e1
Revises: f9a1e5c72d30
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4b8a7d219e1"
down_revision: str | None = "f9a1e5c72d30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("external_operations") as batch_op:
        batch_op.add_column(
            sa.Column("result_refs", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("external_operations") as batch_op:
        batch_op.drop_column("result_refs")
