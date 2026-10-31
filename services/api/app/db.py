"""SQLAlchemy persistence layer.

Default database is SQLite (zero setup, matches the MVP constraint);
DATABASE_URL accepts PostgreSQL without code changes (docker-compose
provides one). Tables, by family:

- protocol_snapshots: daily TVL/risk observations per protocol, enabling
  history beyond DefiLlama's endpoint and point-in-time comparisons.
- onchain_observations: daily on-chain activity per protocol per chain, written
  from the saved Dune query. Kept apart from protocol_snapshots because it has a
  different source, a different grain (slug, chain, date) and a different
  failure mode (a missing chain is 'partial', not 'zero').
- alert_records: durable alert log (in-memory evaluation is idempotent per
  day via deterministic alert ids, so re-runs upsert instead of duplicating).
- chat_chunks: the ask-the-analyst retrieval index.
- users / auth_sessions: local accounts and opaque login sessions.
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


_IS_POSTGRES = get_settings().database_url.startswith("postgresql")


def _chunk_vector_type():
    """Dialect-aware embedding column for ``ChatChunk``.

    On Postgres we use pgvector's native ``Vector(dim)`` type (the compose db
    image enables the extension) so future ANN indexing is available. On SQLite
    (dev / tests, where pgvector does not exist) we store the vector as JSON and
    rank it in-process - the same code path runs either way, only the column
    type differs. The import is guarded so a SQLite install never needs the
    package."""
    if _IS_POSTGRES:  # pragma: no cover - exercised only against Postgres
        from pgvector.sqlalchemy import Vector

        return Vector(get_settings().embedding_dimensions)
    return JSON


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


class OnchainObservation(Base):
    """One on-chain activity observation per (protocol, chain, day).

    Written only by the monitoring pass, from a saved Dune query; read back by
    the research pack. The pack never executes SQL (see docs/architecture.md),
    so opening a page is always free and a Dune outage cannot slow the UI.

    Grain is (slug, chain, date) because that is the grain the query returns.
    The per-protocol total is aggregated on *read*, which is what lets a single
    failed chain surface as ``partial`` instead of quietly shrinking the number.

    Every metric is nullable and stays NULL when Dune returned nothing for it -
    never 0, which would read as "no activity" rather than "no measurement".
    """

    __tablename__ = "onchain_observations"

    id = Column(Integer, primary_key=True)
    slug = Column(String, index=True, nullable=False)
    chain = Column(String, nullable=False)
    date = Column(String, nullable=False)  # ISO date (UTC) of the observation
    active_wallets = Column(Integer)
    tx_count = Column(Integer)
    tx_volume_usd = Column(Float)
    returning_wallets = Column(Integer)
    # Provenance: which Dune execution produced this row. Lets an analyst re-read
    # the exact result set without re-running (and re-paying for) the query.
    execution_id = Column(String)
    fetched_at = Column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("slug", "date", "chain", name="uq_onchain_slug_date_chain"),)


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


class ChatChunk(Base):
    """One indexed passage for the ask-the-analyst RAG chat (roadmap #8).

    The chunk text and its provenance are the source of truth for a citation;
    ``embedding`` is optional (null when indexed offline). ``chunk_id`` is a
    content hash so re-ingesting unchanged text updates the same row instead of
    duplicating it. ``doc_id`` lets us drop every chunk from one source when it
    changes (a rewritten doc section, a protocol pack refreshed)."""

    __tablename__ = "chat_chunks"

    chunk_id = Column(String, primary_key=True)
    doc_id = Column(String, index=True, nullable=False)
    source_type = Column(String)  # "doc" | "evidence"
    source_name = Column(String)
    section = Column(String)
    protocol_slug = Column(String, index=True)
    text = Column(String, nullable=False)
    embedding = Column(_chunk_vector_type())


class User(Base):
    """A local account. Authentication is self-contained (no external IdP), so
    the service keeps working with no network and no third-party account - the
    same degradation contract the rest of the app follows.

    The ABAC attribute bag lives on this row: ``role`` drives RBAC, while
    ``clearance`` / ``allowed_categories`` / ``allowed_chains`` drive the
    attribute predicates. ``["*"]`` (or NULL) means unrestricted."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, index=True, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    display_name = Column(String)
    role = Column(String, nullable=False, default="viewer")
    team = Column(String)
    # 1 = standard, 2 = can see critical-severity evidence, 3 = full.
    clearance = Column(Integer, nullable=False, default=1)
    allowed_categories = Column(JSON)
    allowed_chains = Column(JSON)
    # Integer rather than Boolean so the portable ALTER TABLE fallback in
    # ``_migrate_missing_columns`` can add it to a pre-existing SQLite file.
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True))


class SessionRecord(Base):
    """An opaque login session.

    Only the SHA-256 of the token is stored: a database leak cannot be replayed
    as a valid credential. Rows are deleted on logout and expire on their own
    (``expires_at``), so revocation is a DELETE rather than waiting out a JWT.
    Named ``SessionRecord`` to avoid colliding with ``sqlalchemy.orm.Session``."""

    __tablename__ = "auth_sessions"

    token_hash = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True), nullable=False)


_settings = get_settings()
_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    # pgvector's ``Vector`` column type requires the extension to exist before
    # ``create_all`` builds chat_chunks. Ensure it on Postgres (the compose db
    # image ships the extension binary); best-effort so a non-superuser or a
    # non-pgvector deployment degrades to chat running lexical-only rather than
    # crashing startup. SQLite (dev/tests) has no such concept and skips this.
    if _IS_POSTGRES:  # pragma: no cover - exercised only against Postgres
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception as exc:  # noqa: BLE001 - surface, don't block startup
            logger.warning(
                "Could not enable pgvector extension (%s); chat will use lexical retrieval",
                type(exc).__name__,
            )
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
