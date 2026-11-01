"""SQLAlchemy persistence layer.

Default database is SQLite (zero setup, matches the MVP constraint);
DATABASE_URL accepts PostgreSQL without code changes (docker-compose
provides one). Tables, by family:

- protocol_catalog: the discovery catalog - one row per DefiLlama slug, the
  stable unique identifier. Held apart from protocol_snapshots because it is a
  different grain (identity/metadata, not a daily observation) and a different
  cadence (metadata sync, not the analytics pass). Most catalog protocols are
  discovered but never monitored, so the analysis columns stay NULL until a
  scoring pass fills them - a gap, never a zero.
- protocol_catalog_chains: normalized (slug, chain) membership so "protocols on
  chain X" is an indexed exact match rather than a substring scan of a JSON blob.
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
    Index,
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
    # --- Full research-payload persistence (DB-first detail, latency sweep) ---
    # The detail page used to rebuild these fields by crawling DefiLlama on the
    # request path (~13 s cold). They are now captured at crawl time by the
    # monitoring/pre-seed pass so GET /api/protocols/{slug} assembles entirely
    # from this row. Every column is nullable and NULL always means "never
    # captured" - a gap, never a zero (honesty contract).
    fees_1d = Column(Float)
    fees_30d = Column(Float)
    revenue_1d = Column(Float)
    volume_1d = Column(Float)
    fees_tvl = Column(Float)
    volume_tvl = Column(Float)
    depeg_worst_bps = Column(Float)
    depeg_asset = Column(String)
    # {chain: tvl} at capture time - the research payload's chain breakdown.
    chain_shares = Column(JSON)
    # scoring.RiskAssessment.to_dict() in full (indicators + data_gaps), so the
    # explainable-risk panel renders without a live rescore.
    risk_json = Column(JSON)
    # 1 = written by a watchlist monitoring pass (feeds the board). 0 = written
    # by the catalog pre-seed pass: persisted for detail reads but deliberately
    # invisible to dashboard aggregates/staleness, so CEX/Bridge rows cannot
    # distort board totals or keep a stale board looking fresh.
    monitored = Column(Integer, nullable=False, default=1)

    # A protocol should have at most one snapshot per day. This guards against
    # duplicate (slug, date) rows from concurrent monitoring passes, which would
    # otherwise double-count aggregate stats and appear twice in the board.
    __table_args__ = (
        UniqueConstraint("slug", "date", name="uq_snapshot_slug_date"),
        # Latest-row-per-slug and trailing-series reads on the DB-first detail
        # path; (slug, date) ordering lets both walk the index directly.
        Index("ix_snapshot_slug_date", "slug", "date"),
    )


# Postgres-only catalog search accelerators. The Phase 0 perf baseline showed
# `%term%` catalog search degrades to a sequential scan as the catalog grows
# (p95 ~130 ms at 100k). A trigram GIN lets PostgreSQL answer the existing
# ILIKE from an index. Declared ONLY on Postgres: SQLite cannot use a GIN and
# its scan is already sub-millisecond at current size, so we do not over-index
# there (plan: "add indexes only where a query pattern justifies them"). Also
# re-issued idempotently in init_db() so a persisted Postgres volume predating
# them is accelerated without a full alembic run.
_catalog_trgm_indexes: tuple = ()
if _IS_POSTGRES:  # pragma: no cover - exercised only against Postgres
    _catalog_trgm_indexes = (
        Index(
            "ix_protocol_catalog_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_protocol_catalog_slug_trgm",
            "slug",
            postgresql_using="gin",
            postgresql_ops={"slug": "gin_trgm_ops"},
        ),
    )


class ProtocolCatalog(Base):
    """The protocol discovery catalog: one row per DefiLlama slug.

    Discovery is deliberately separated from monitoring. This table is filled by
    an idempotent metadata sync off the ``/protocols`` directory (thousands of
    protocols), while ``protocol_snapshots`` only ever holds the small set a
    monitoring pass actually scores. The provider slug is the primary key, so a
    re-sync updates in place instead of duplicating, and rows absent from a
    provider response are left untouched (a delisting must not erase history).

    The analysis columns (``risk_score`` / ``risk_band`` / ``monitored``) are
    written by the monitoring pass, never by discovery, and stay NULL for the
    many catalog protocols with no Dune coverage or score - which is exactly the
    state the Explorer must be able to represent honestly."""

    __tablename__ = "protocol_catalog"

    slug = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    category = Column(String, index=True)
    symbol = Column(String)
    tvl = Column(Float, index=True)
    change_1d = Column(Float)
    change_7d = Column(Float)
    change_1m = Column(Float)
    audits = Column(String)
    url = Column(String)
    listing_timestamp = Column(Integer)
    # Normalized, de-duplicated display list of chains. Filtering by chain uses
    # the ``protocol_catalog_chains`` join table, not this blob.
    chains = Column(JSON)
    # Analysis lives here only so the catalog can sort/show an *available* risk
    # score; NULL means "never scored", not "scored zero". See honesty contract.
    risk_score = Column(Float, index=True)
    risk_band = Column(String)
    monitored = Column(Integer, nullable=False, default=0)
    first_seen_at = Column(DateTime(timezone=True))
    # Metadata sync time of the row - the "updated date" the Explorer sorts on.
    updated_at = Column(DateTime(timezone=True), index=True)
    last_synced_at = Column(DateTime(timezone=True))

    # Empty on SQLite; the two Postgres-only trigram GINs otherwise.
    __table_args__ = _catalog_trgm_indexes


class ProtocolCatalogChain(Base):
    """(slug, chain) membership, one row per chain a catalog protocol spans.

    Composite primary key indexes (slug, chain); a chain-leading index backs the
    common "filter by chain" lookup. Rebuilt per protocol only when its chain
    set changes, so a steady-state sync writes nothing here."""

    __tablename__ = "protocol_catalog_chains"

    slug = Column(String, primary_key=True)
    chain = Column(String, primary_key=True)

    __table_args__ = (Index("ix_catalog_chains_chain", "chain"),)


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
if _IS_POSTGRES:
    # PostgreSQL deployment: pool_pre_ping re-validates a connection before use
    # (a container restart would otherwise hand back a dead socket), pool_recycle
    # bounds idle-connection lifetime under a proxy/LB, and an explicit pool
    # ceiling keeps concurrent dashboard reads from exhausting Postgres backends.
    # SQLite (dev/tests) has no such concern and keeps its single-connection
    # check_same_thread escape hatch untouched.
    engine = create_engine(
        _settings.database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
    )
else:
    engine = create_engine(
        _settings.database_url,
        connect_args={"check_same_thread": False},
    )
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
                # pg_trgm must exist before create_all builds the catalog GINs.
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception as exc:  # noqa: BLE001 - surface, don't block startup
            logger.warning(
                "Could not enable Postgres extensions (%s); chat will use lexical "
                "retrieval and catalog search stays scan-backed",
                type(exc).__name__,
            )
    Base.metadata.create_all(engine)
    _migrate_missing_columns()
    if _IS_POSTGRES:  # pragma: no cover - exercised only against Postgres
        _ensure_catalog_search_indexes()


def _ensure_catalog_search_indexes() -> None:  # pragma: no cover - Postgres-only
    """``create_all`` builds the trigram GINs for a *fresh* Postgres catalog, but
    a persisted volume created before they existed keeps its table (create_all
    never ALTERs one). Re-issue them idempotently so an existing deployment is
    accelerated too, without a manual alembic run. Best-effort: a missing
    extension or an older Postgres degrades to the ordinary scan, never a crash.
    """
    ddl = (
        "CREATE INDEX IF NOT EXISTS ix_protocol_catalog_name_trgm "
        "ON protocol_catalog USING gin (name gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS ix_protocol_catalog_slug_trgm "
        "ON protocol_catalog USING gin (slug gin_trgm_ops)",
    )
    try:
        with engine.begin() as conn:
            for stmt in ddl:
                conn.execute(text(stmt))
    except Exception as exc:  # noqa: BLE001 - accelerator is optional
        logger.warning(
            "Could not ensure catalog trigram indexes (%s); search stays scan-backed",
            type(exc).__name__,
        )


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
                # Portable stand-in for the alembic revision's server_default:
                # ALTER ADD COLUMN cannot carry NOT NULL DEFAULT across both
                # dialects, so a pre-seed snapshot row lands as NULL - which the
                # board's ``monitored == 1`` filter would silently hide. Every
                # row predating the column was written by a monitoring pass, so
                # backfill it as monitored.
                if table.name == "protocol_snapshots" and col.name == "monitored":
                    conn.execute(
                        text("UPDATE protocol_snapshots SET monitored = 1 WHERE monitored IS NULL")
                    )


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
