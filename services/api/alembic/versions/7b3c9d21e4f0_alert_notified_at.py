"""alert notified_at delivery marker

Adds ``alert_records.notified_at`` so the alert-delivery fan-out can dedup /
honour a cooldown keyed on the deterministic per-day alert id.

Revision ID: 7b3c9d21e4f0
Revises: d48800564d8e
Create Date: 2026-10-29 16:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b3c9d21e4f0"
down_revision: str | None = "d48800564d8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alert_records",
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_records", "notified_at")
