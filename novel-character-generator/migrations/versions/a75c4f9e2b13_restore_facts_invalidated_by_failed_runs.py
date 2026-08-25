"""restore facts invalidated by failed extraction runs

Revision ID: a75c4f9e2b13
Revises: f64b3e8d0a21
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "a75c4f9e2b13"
down_revision: str | None = "f64b3e8d0a21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    runs = sa.Table("pipeline_runs", sa.MetaData(), autoload_with=bind)
    observations = sa.Table("feature_observations", sa.MetaData(), autoload_with=bind)
    failed_run_ids = sa.select(runs.c.id).where(
        runs.c.run_type == "text_analysis",
        runs.c.status.in_(("failed", "cancelled")),
    )
    now = datetime.now(UTC)

    # Legacy workers superseded the previous usable snapshot before extraction
    # completed. Restore exactly the facts invalidated by those failed runs.
    bind.execute(
        observations.update()
        .where(
            observations.c.invalidated_by_run_id.in_(failed_run_ids),
            observations.c.record_status == "superseded",
            observations.c.extraction_run_id != observations.c.invalidated_by_run_id,
        )
        .values(
            record_status="active",
            valid_to=None,
            invalidated_at=None,
            invalidated_by_run_id=None,
            updated_at=now,
        )
    )


def downgrade() -> None:
    # This is a corrective data migration. Re-introducing the invalid state is unsafe.
    return None
