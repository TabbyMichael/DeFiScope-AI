"""snapshot research-payload columns

Extends ``protocol_snapshots`` with every field the protocol detail page used
to rebuild by crawling DefiLlama on the request path: fee/revenue/volume
enrichment, the depeg watch, the chain breakdown and the full explainable-risk
JSON. Also adds ``monitored`` (1 = watchlist pass, feeds the board; 0 = catalog
pre-seed, detail-only) and a ``(slug, date)`` index for the latest-row and
trailing-series reads of the DB-first detail path.

Existing rows are backfilled ``monitored = 1`` so the board's population is
unchanged by the upgrade. All new analytic columns stay NULL on historical rows
- "never captured", never a zero.

Revision ID: f2d6b81c4a95
Revises: e5b1c4d27a90
Create Date: 2026-10-31 23:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2d6b81c4a95"
down_revision: str | None = "e5b1c4d27a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON_TYPE = sa.JSON()


def upgrade() -> None:
    op.add_column("protocol_snapshots", sa.Column("fees_1d", sa.Float(), nullable=True))
    op.add_column("protocol_snapshots", sa.Column("fees_30d", sa.Float(), nullable=True))
    op.add_column("protocol_snapshots", sa.Column("revenue_1d", sa.Float(), nullable=True))
    op.add_column("protocol_snapshots", sa.Column("volume_1d", sa.Float(), nullable=True))
    op.add_column("protocol_snapshots", sa.Column("fees_tvl", sa.Float(), nullable=True))
    op.add_column("protocol_snapshots", sa.Column("volume_tvl", sa.Float(), nullable=True))
    op.add_column("protocol_snapshots", sa.Column("depeg_worst_bps", sa.Float(), nullable=True))
    op.add_column("protocol_snapshots", sa.Column("depeg_asset", sa.String(), nullable=True))
    op.add_column("protocol_snapshots", sa.Column("chain_shares", _JSON_TYPE, nullable=True))
    op.add_column("protocol_snapshots", sa.Column("risk_json", _JSON_TYPE, nullable=True))
    op.add_column(
        "protocol_snapshots",
        sa.Column("monitored", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_snapshot_slug_date", "protocol_snapshots", ["slug", "date"])


def downgrade() -> None:
    op.drop_index("ix_snapshot_slug_date", table_name="protocol_snapshots")
    op.drop_column("protocol_snapshots", "monitored")
    op.drop_column("protocol_snapshots", "risk_json")
    op.drop_column("protocol_snapshots", "chain_shares")
    op.drop_column("protocol_snapshots", "depeg_asset")
    op.drop_column("protocol_snapshots", "depeg_worst_bps")
    op.drop_column("protocol_snapshots", "volume_tvl")
    op.drop_column("protocol_snapshots", "fees_tvl")
    op.drop_column("protocol_snapshots", "volume_1d")
    op.drop_column("protocol_snapshots", "revenue_1d")
    op.drop_column("protocol_snapshots", "fees_30d")
    op.drop_column("protocol_snapshots", "fees_1d")
