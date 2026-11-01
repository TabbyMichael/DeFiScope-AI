"""protocol_catalog: 5,000+ protocol discovery catalog with server-side paging

Separates protocol *discovery* (this catalog, synced from the DefiLlama
directory) from *monitoring* (protocol_snapshots, scored by the analytics pass).
One row per provider slug - the stable unique identifier - so ingestion is an
idempotent upsert rather than an insert, and rows a provider stops returning are
left in place rather than deleted.

The analysis columns (risk_score / risk_band / monitored) are nullable on
purpose: the catalog is far larger than the monitored set, and an unscored
protocol is a data gap, never a zero.

A normalized (slug, chain) join table makes \"filter by chain\" an indexed exact
match instead of a substring scan of a JSON column.

Revision ID: e5b1c4d27a90
Revises: c4f2a71b93de
Create Date: 2026-10-31 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b1c4d27a90"
down_revision: str | None = "c4f2a71b93de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATALOG = "protocol_catalog"
_CHAINS = "protocol_catalog_chains"


def upgrade() -> None:
    op.create_table(
        _CATALOG,
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("tvl", sa.Float(), nullable=True),
        sa.Column("change_1d", sa.Float(), nullable=True),
        sa.Column("change_7d", sa.Float(), nullable=True),
        sa.Column("change_1m", sa.Float(), nullable=True),
        sa.Column("audits", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("listing_timestamp", sa.Integer(), nullable=True),
        sa.Column("chains", sa.JSON(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("risk_band", sa.String(), nullable=True),
        sa.Column("monitored", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("slug"),
    )
    # Indexes for the Explorer's common filters and sort columns. Names follow
    # SQLAlchemy's ix_<table>_<column> convention so ``create_all`` and this
    # migration agree and ``alembic revision --autogenerate`` stays clean.
    op.create_index(op.f("ix_protocol_catalog_name"), _CATALOG, ["name"], unique=False)
    op.create_index(op.f("ix_protocol_catalog_category"), _CATALOG, ["category"], unique=False)
    op.create_index(op.f("ix_protocol_catalog_tvl"), _CATALOG, ["tvl"], unique=False)
    op.create_index(op.f("ix_protocol_catalog_risk_score"), _CATALOG, ["risk_score"], unique=False)
    op.create_index(op.f("ix_protocol_catalog_updated_at"), _CATALOG, ["updated_at"], unique=False)

    op.create_table(
        _CHAINS,
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("chain", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("slug", "chain"),
    )
    op.create_index("ix_catalog_chains_chain", _CHAINS, ["chain"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_catalog_chains_chain", table_name=_CHAINS)
    op.drop_table(_CHAINS)
    op.drop_index(op.f("ix_protocol_catalog_updated_at"), table_name=_CATALOG)
    op.drop_index(op.f("ix_protocol_catalog_risk_score"), table_name=_CATALOG)
    op.drop_index(op.f("ix_protocol_catalog_tvl"), table_name=_CATALOG)
    op.drop_index(op.f("ix_protocol_catalog_category"), table_name=_CATALOG)
    op.drop_index(op.f("ix_protocol_catalog_name"), table_name=_CATALOG)
    op.drop_table(_CATALOG)
