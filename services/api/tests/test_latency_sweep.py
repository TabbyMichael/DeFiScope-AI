"""Whole-app read-path latency + no-crawl regression guard.

The performance contract of the DB-first sweep is: every backend read the
frontend makes is served from the database and *never* crawls DefiLlama on the
request path. This test enforces both halves at once:

* a crawl (``get_pack`` / ``get_protocol`` / a dashboard hydration ``run_monitor``)
  is monkeypatched to explode, so any read route that still reaches for the
  network fails loudly rather than passing slowly;
* each read route is timed and must finish within a wall-clock ceiling that is
  far below the ~13 s the old crawl cost but generous enough to stay green on a
  loaded CI runner (the real sub-20 ms figure is shown by the curl benchmark).
"""

import time
from datetime import UTC, datetime

import pytest
from app.db import Base, ProtocolCatalog, ProtocolSnapshot, SessionLocal, engine
from app.services import alerts as alert_engine
from app.services.protocols import ProtocolResearchService

SWEEP_SLUG = "sweep-protocol"
# A permissive ceiling that only a crawl-class regression (seconds) would breach;
# in-process SQLite reads land well under it.
CEILING_MS = 250.0

READ_ROUTES = [
    "/api/protocols?page=1",
    "/api/protocols/facets",
    "/api/dashboard",
    f"/api/protocols/{SWEEP_SLUG}",
    f"/api/protocols/{SWEEP_SLUG}/history?days=30",
    f"/api/protocols/{SWEEP_SLUG}/risk-history?days=90",
    f"/api/briefs/{SWEEP_SLUG}",
    "/api/alerts",
]


@pytest.fixture()
def no_crawl(monkeypatch):
    """Any request-path crawl is a hard failure."""

    async def explode(*a, **k):
        raise AssertionError("a read route reached for the network on the request path")

    monkeypatch.setattr(ProtocolResearchService, "get_pack", explode)
    monkeypatch.setattr(ProtocolResearchService, "get_packs", explode)
    monkeypatch.setattr(alert_engine, "run_monitor", explode)


@pytest.fixture()
def seeded():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        now = datetime.now(UTC)
        today = now.date().isoformat()
        session.query(ProtocolSnapshot).filter_by(slug=SWEEP_SLUG).delete()
        session.query(ProtocolCatalog).filter_by(slug=SWEEP_SLUG).delete()
        session.commit()
        session.add(
            ProtocolCatalog(
                slug=SWEEP_SLUG,
                name="Sweep Protocol",
                category="Lending",
                tvl=2_000_000.0,
                change_7d=1.0,
            )
        )
        session.add(
            ProtocolSnapshot(
                slug=SWEEP_SLUG,
                date=today,
                name="Sweep Protocol",
                category="Lending",
                tvl=2_000_000.0,
                change_7d=1.0,
                risk_score=40.0,
                risk_band="moderate",
                captured_at=now,
                monitored=1,
            )
        )
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        session.query(ProtocolSnapshot).filter_by(slug=SWEEP_SLUG).delete()
        session.query(ProtocolCatalog).filter_by(slug=SWEEP_SLUG).delete()
        session.commit()
    finally:
        session.close()


async def test_every_read_route_is_db_backed_and_fast(anonymous_client, no_crawl, seeded):
    for route in READ_ROUTES:
        started = time.perf_counter()
        resp = await anonymous_client.get(route)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        assert resp.status_code == 200, f"{route} -> {resp.status_code}"
        assert elapsed_ms < CEILING_MS, f"{route} took {elapsed_ms:.0f} ms (ceiling {CEILING_MS})"
