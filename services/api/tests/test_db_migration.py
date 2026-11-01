"""Guard for the Critical #1 fix: init_db() must add columns introduced to a
model *after* a database already exists (create_all never ALTERs a table)."""

import pytest
from app.db import (
    Base,
    OnchainObservation,
    ProtocolSnapshot,
    SessionLocal,
    _migrate_missing_columns,
    engine,
    init_db,
)
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_trgm_index_ddl_is_valid_postgres():
    """The search accelerator only activates on Postgres, which the SQLite test
    engine can never exercise. Assert the exact DDL shape compiles to a valid
    trigram GIN for PostgreSQL - against a throwaway table, so the shared
    ``ProtocolCatalog`` metadata is never mutated by this test."""
    from sqlalchemy import Column, Index, MetaData, String, Table
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex

    scratch = MetaData()
    table = Table("scratch_catalog", scratch, Column("name", String))
    idx = Index(
        "ix_scratch_name_trgm",
        table.c.name,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    ddl = str(CreateIndex(idx).compile(dialect=postgresql.dialect()))
    assert "USING gin" in ddl
    assert "gin_trgm_ops" in ddl


def test_catalog_trgm_indexes_match_dialect():
    """The Phase 0 baseline justified a Postgres-only trigram GIN for search. On
    SQLite that accelerator must be absent (no over-indexing); on Postgres it
    must be present and built by init_db(). Assert whichever the test engine is.
    """
    Base.metadata.drop_all(engine)
    init_db()  # must not raise on either dialect
    try:
        insp = inspect(engine)
        assert "protocol_catalog" in insp.get_table_names()
        index_names = {i["name"] for i in insp.get_indexes("protocol_catalog")}
        trgm_present = "ix_protocol_catalog_name_trgm" in index_names
        if engine.dialect.name == "postgresql":
            assert trgm_present, "Postgres must build the search accelerator"
        else:
            assert not trgm_present, "SQLite must stay lean (no GIN)"
        # The ordinary, portable indexes the Explorer relies on are always there.
        assert "ix_protocol_catalog_name" in index_names
        assert "ix_protocol_catalog_tvl" in index_names
    finally:
        Base.metadata.drop_all(engine)


def test_init_db_adds_missing_columns_to_existing_table():
    # Recreate ONLY the pre-change (legacy) schema, as an already-deployed DB
    # would have: the new rich columns are absent.
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE protocol_snapshots (
                    id INTEGER PRIMARY KEY,
                    slug VARCHAR NOT NULL,
                    date VARCHAR NOT NULL,
                    tvl FLOAT,
                    staking_tvl FLOAT,
                    risk_score FLOAT,
                    risk_band VARCHAR,
                    captured_at DATETIME
                )
                """
            )
        )
        # A legacy row that must survive the migration.
        conn.execute(
            text(
                "INSERT INTO protocol_snapshots (slug, date, tvl) "
                "VALUES ('aave', '2026-01-01', 123.0)"
            )
        )

    before = {c["name"] for c in inspect(engine).get_columns("protocol_snapshots")}
    assert "name" not in before and "change_7d" not in before  # sanity

    init_db()  # create_all is a no-op (table exists); migration must ALTER

    after = {c["name"] for c in inspect(engine).get_columns("protocol_snapshots")}
    for col in (
        "name",
        "category",
        "change_7d",
        "change_30d",
        "volatility_30d",
        "top_chain",
        "top_chain_share",
        "incentive_ratio",
        "stale_days",
    ):
        assert col in after, f"{col} was not added by the migration"

    # The legacy row is preserved (now with NULLs for the new columns).
    with engine.begin() as conn:
        row = conn.execute(text("SELECT slug, tvl, name FROM protocol_snapshots")).one()
    assert row.slug == "aave" and float(row.tvl) == 123.0 and row.name is None

    # And the ORM can now read/write the enriched model against that table.
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        s.add(ProtocolSnapshot(slug="defi", date="2026-01-02", name="DeFi", tvl=5.0, change_7d=1.5))
        s.commit()
        assert s.query(ProtocolSnapshot).filter_by(slug="defi").one().change_7d == 1.5
    finally:
        s.close()

    Base.metadata.drop_all(engine)


def test_migrate_is_idempotent():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    cols_before = {c["name"] for c in inspect(engine).get_columns("protocol_snapshots")}
    _migrate_missing_columns()  # nothing missing -> no-op, must not raise
    _migrate_missing_columns()
    cols_after = {c["name"] for c in inspect(engine).get_columns("protocol_snapshots")}
    assert cols_before == cols_after
    Base.metadata.drop_all(engine)


def test_init_db_creates_onchain_table_on_legacy_store():
    """A store created before the Dune integration existed has no
    onchain_observations table. create_all() adds missing *tables*, so startup
    must leave the deployment usable without an explicit alembic run."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    OnchainObservation.__table__.drop(engine)  # as an older deploy would be
    assert "onchain_observations" not in inspect(engine).get_table_names()

    init_db()

    assert "onchain_observations" in inspect(engine).get_table_names()
    cols = {c["name"] for c in inspect(engine).get_columns("onchain_observations")}
    assert {
        "slug",
        "chain",
        "date",
        "active_wallets",
        "tx_count",
        "tx_volume_usd",
        "returning_wallets",
        "execution_id",
        "fetched_at",
    } <= cols
    Base.metadata.drop_all(engine)


def test_onchain_observation_grain_is_slug_date_chain():
    """One row per protocol/chain/day: a re-run must not double-count, while a
    second chain on the same day is a legitimately separate row."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        session.add(
            OnchainObservation(slug="aave-v3", chain="ethereum", date="2026-10-30", tx_count=10)
        )
        session.commit()
        session.add(
            OnchainObservation(slug="aave-v3", chain="ethereum", date="2026-10-30", tx_count=11)
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            OnchainObservation(slug="aave-v3", chain="arbitrum", date="2026-10-30", tx_count=3)
        )
        session.commit()
        assert session.query(OnchainObservation).filter_by(slug="aave-v3").count() == 2
    finally:
        session.close()
        Base.metadata.drop_all(engine)
