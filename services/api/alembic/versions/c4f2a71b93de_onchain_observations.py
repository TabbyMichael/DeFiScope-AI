"""onchain_observations: daily on-chain activity from Dune Analytics

Creates the table the monitoring pass writes from a saved Dune query and the
research pack reads back. Grain is (slug, chain, date) - the grain the query
returns - so the per-protocol total can be aggregated on read and a single
failed chain surfaces as "partial" instead of quietly shrinking the number.

Every metric column is nullable on purpose: NULL means "Dune returned nothing
for this metric", which is a data gap. Zero would mean "no activity" instead.

Revision ID: c4f2a71b93de
Revises: c4f1a7d9e230
Create Date: 2026-10-30 15:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f2a71b93de"
down_revision: str | None = "c4f1a7d9e230"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "onchain_observations"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("chain", sa.String(), nullable=False),
        sa.Column("date", sa.String(), nullable=False),
        sa.Column("active_wallets", sa.Integer(), nullable=True),
        sa.Column("tx_count", sa.Integer(), nullable=True),
        sa.Column("tx_volume_usd", sa.Float(), nullable=True),
        sa.Column("returning_wallets", sa.Integer(), nullable=True),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", "date", "chain", name="uq_onchain_slug_date_chain"),
    )
    op.create_index(op.f("ix_onchain_observations_slug"), _TABLE, ["slug"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_onchain_observations_slug"), table_name=_TABLE)
    op.drop_table(_TABLE)
