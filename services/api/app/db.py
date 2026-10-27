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

from collections.abc import Iterator

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class ProtocolSnapshot(Base):
    __tablename__ = "protocol_snapshots"

    id = Column(Integer, primary_key=True)
    slug = Column(String, index=True, nullable=False)
    date = Column(String, nullable=False)  # ISO date of the observation
    tvl = Column(Float)
    staking_tvl = Column(Float)
    risk_score = Column(Float)
    risk_band = Column(String)
    captured_at = Column(DateTime(timezone=True))

    __table_args__ = ()


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


_settings = get_settings()
_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
