"""SQLAlchemy persistence layer.

Default database is SQLite (zero setup, matches the MVP constraint);
DATABASE_URL accepts PostgreSQL without code changes (docker-compose
provides one). Two tables:

- protocol_snapshots: daily TVL/risk observations per protocol, enabling
  history beyond DefiLlama's endpoint and point-in-time comparisons.
- alert_records: durable alert log (in-memory evaluation is idempotent per
  day via deterministic alert ids, so re-runs upsert instead of duplicating).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class ProtocolSnapshot(Base):
    """One daily observation per protocol. Persists the full normalized
    overview so the dashboard can render entirely from the DB (DB-first)
    rather than re-hitting DefiLlama on every page load. History rows also
    back sparklines and point-in-time deltas."""

    __tablename__ = "protocol_snapshots"

    id = Column(Integer, primary_key=True)
    slug = Column(String, index=True, nullable=False)
    date = Column(String, nullable=False)  # ISO date of the observation
    name = Column(String)
    category = Column(String)
    tvl = Column(Float)
    staking_tvl = Column(Float)
    change_7d = Column(Float)
    change_30d = Column(Float)
    volatility_30d = Column(Float)
    top_chain = Column(String)
    top_chain_share = Column(Float)
    incentive_ratio = Column(Float)
    stale_days = Column(Integer)
    risk_score = Column(Float)
    risk_band = Column(String)
    captured_at = Column(DateTime(timezone=True))

    # A protocol should have at most one snapshot per day. This guards against
    # duplicate (slug, date) rows from concurrent monitoring passes, which would
    # otherwise double-count aggregate stats and appear twice in the board.
    __table_args__ = (UniqueConstraint("slug", "date", name="uq_snapshot_slug_date"),)


class AlertRecord(Base):
    __tablename__ = "alert_records"

    id = Column(String, primary_key=True)
    slug = Column(String, index=True, nullable=False)
    protocol = Column(String)
    rule = Column(String)
    severity = Column(String)
    message = Column(String)
    evidence = Column(JSON)
    triggered_at = Column(String)
    # Delivery marker: when this alert was last fanned out to notifiers. Null
    # until first send; drives the cooldown/dedup so re-runs and the 30-min
    # scheduler do not spam the same protocol/rule/day alert.
    notified_at = Column(DateTime(timezone=True))


_settings = get_settings()
_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate_missing_columns()


# Map ORM column type class names to SQL types valid on both SQLite and
# PostgreSQL.
_SQL_TYPES = {
    "Float": "FLOAT",
    "Integer": "INTEGER",
    "JSON": "JSON",
    "DateTime": "TIMESTAMP",
}


def _migrate_missing_columns() -> None:
    """``create_all()`` only creates missing *tables*; it never ``ALTER``s an
    existing one. So when new columns are added to a model after a database was
    first created (e.g. the richer ProtocolSnapshot fields), an existing SQLite
    file or a persisted Postgres volume would be missing them and every read /
    write would fail. This adds any model column not yet present, idempotently.

    A full migration tool (Alembic) is now configured (``services/api/alembic``,
    baseline revision creates both tables) and is the source of truth for schema
    changes. This in-process guard remains as a safety net for databases created
    before a given column existed - e.g. a persisted SQLite file or Postgres
    volume that predates a deploy - so ``init_db()`` keeps an un-migrated store
    usable without blocking startup on ``alembic upgrade head``."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if table.name not in table_names:
                continue  # create_all just made it with all columns
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                sqltype = _SQL_TYPES.get(col.type.__class__.__name__, "VARCHAR")
                logger.info("Migrating: adding column %s.%s", table.name, col.name)
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {sqltype}"))


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
