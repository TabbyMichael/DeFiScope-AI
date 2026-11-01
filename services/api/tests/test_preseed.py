"""Catalog pre-seed pass: warm detail pages without touching the board.

Two contracts these tests pin down:

* the seed queue is exactly "catalog rows with no snapshot", biggest first, and
  ``run_batch`` persists its captures as **unmonitored** rows and emits no alerts;
* unmonitored rows are invisible to every dashboard aggregate and the staleness
  clock - the whole point of the ``monitored`` tag is that pre-seeding a CEX/Bridge
  total can never move the board's numbers or keep a stale board looking fresh.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.config import get_settings
from app.db import Base, ProtocolCatalog, ProtocolSnapshot, SessionLocal, engine
from app.services import alerts, preseed
from app.services import dashboard as dash
from app.services.protocols import ProtocolResearchService

SEED_SLUGS = ("preseed-a", "preseed-b", "preseed-board")
CHUNK_SLUGS = tuple(f"preseed-chunk-{i}" for i in range(5))


@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.query(ProtocolSnapshot).filter(
            ProtocolSnapshot.slug.in_((*SEED_SLUGS, *CHUNK_SLUGS))
        ).delete(synchronize_session=False)
        session.query(ProtocolCatalog).filter(
            ProtocolCatalog.slug.in_((*SEED_SLUGS, *CHUNK_SLUGS))
        ).delete(synchronize_session=False)
        session.commit()
        session.close()


def _catalog(session, slug, tvl):
    session.merge(ProtocolCatalog(slug=slug, name=slug, tvl=tvl, category="Lending"))


def _snapshot(session, slug, tvl, monitored):
    session.add(
        ProtocolSnapshot(
            slug=slug,
            date="2026-01-05",
            name=slug,
            tvl=tvl,
            captured_at=datetime.now(UTC),
            monitored=monitored,
        )
    )


def test_queue_is_unseeded_catalog_biggest_first(db):
    _catalog(db, "preseed-a", 1e9)
    _catalog(db, "preseed-b", 5e8)
    _snapshot(db, "preseed-b", 5e8, monitored=1)  # already seeded -> excluded
    db.commit()

    # Above a floor only preseed-a clears; it is the sole unseeded big name.
    assert preseed.unseeded_slugs(db, limit=10, min_tvl=1e8) == ["preseed-a"]
    # Floor 0 brings in the rest, ordered by TVL descending.
    assert preseed.unseeded_slugs(db, limit=10, min_tvl=0.0) == ["preseed-a"]


async def test_run_batch_persists_unmonitored_and_emits_no_alerts(db, monkeypatch):
    _catalog(db, "preseed-a", 1e9)
    db.commit()

    captured = {}

    async def fake_get_packs(self, slugs, http, session=None):
        captured["slugs"] = list(slugs)
        return [SimpleNamespace(slug=s) for s in slugs]

    def fake_backfill(session, pack, monitored=1):
        captured["backfill_monitored"] = monitored

    def fake_persist(session, packs, monitored=1):
        captured["monitored"] = monitored
        captured["count"] = len(packs)

    # Keep the crawl + writes in-memory: the queue/persist wiring is what matters,
    # the network pack build is covered by the monitoring tests.
    monkeypatch.setattr(ProtocolResearchService, "get_packs", fake_get_packs)
    monkeypatch.setattr(alerts, "backfill_history", fake_backfill)
    monkeypatch.setattr(alerts, "persist_snapshots", fake_persist)
    monkeypatch.setattr(
        preseed,
        "pack_to_overview",
        lambda p: SimpleNamespace(risk_score=None, risk_band=None),
    )
    from app.services import catalog

    monkeypatch.setattr(catalog, "refresh_analysis", lambda session, scored: 0)

    result = await preseed.run_batch(ProtocolResearchService(), None, db)

    assert result == 1
    assert captured["slugs"] == ["preseed-a"]
    # The seed writes detail-only rows and never claims the board.
    assert captured["monitored"] == 0
    # History backfill is stamped the same way, or its rows leak onto the board.
    assert captured["backfill_monitored"] == 0


async def test_run_batch_crawls_in_chunks_to_keep_the_loop_responsive(db, monkeypatch):
    # Regression: one unbroken 150-protocol gather monopolised the single
    # uvicorn event loop for seconds at a stretch, so interactive requests
    # (login) queued behind it until the web proxy timed out. The crawl must
    # go out in preseed_chunk_size pieces, each its own awaited batch.
    for i, slug in enumerate(CHUNK_SLUGS):
        _catalog(db, slug, (5 - i) * 1e9)
    db.commit()

    calls: list[list[str]] = []

    async def fake_get_packs(self, slugs, http, session=None):
        calls.append(list(slugs))
        return [SimpleNamespace(slug=s) for s in slugs]

    monkeypatch.setattr(ProtocolResearchService, "get_packs", fake_get_packs)
    monkeypatch.setattr(alerts, "backfill_history", lambda *a, **k: None)
    monkeypatch.setattr(alerts, "persist_snapshots", lambda *a, **k: None)
    monkeypatch.setattr(
        preseed,
        "pack_to_overview",
        lambda p: SimpleNamespace(risk_score=None, risk_band=None),
    )
    from app.services import catalog

    monkeypatch.setattr(catalog, "refresh_analysis", lambda session, scored: 0)
    settings = get_settings()
    monkeypatch.setattr(settings, "preseed_chunk_size", 2)
    monkeypatch.setattr(settings, "preseed_chunk_pause_seconds", 0.0)

    result = await preseed.run_batch(ProtocolResearchService(), None, db, limit=5, min_tvl=0.0)

    assert result == 5
    # 5 slugs at chunk size 2 -> three bounded calls, nothing bigger.
    assert [len(c) for c in calls] == [2, 2, 1]
    # Chunks walk the queue in order and cover it exactly once.
    assert sum(calls, []) == preseed.unseeded_slugs(db, 5, 0.0)


def test_backfill_history_stamps_preseed_rows_unmonitored(db):
    # Regression: ``run_batch`` calls the *real* backfill_history before
    # persist_snapshots. If backfilled TVL days inherit the column default
    # (monitored=1) they leak into board aggregates even though the latest row
    # is tagged monitored=0 - the guard filters per row, not per slug.
    import pandas as pd

    df = pd.DataFrame({"tvl": [1e6, 2e6, 3e6]}, index=pd.date_range("2026-01-01", periods=3))
    pack = SimpleNamespace(
        slug="preseed-a",
        detail=SimpleNamespace(name="preseed-a"),
        tvl_df=df,
        latest_date=str(df.index.max().date()),  # newest day is persist's job, not backfill's
    )

    alerts.backfill_history(db, pack, monitored=0)

    seeded = db.query(ProtocolSnapshot).filter_by(slug="preseed-a").all()
    assert seeded, "backfill should have written the historical days"
    # Every backfilled row must carry the caller's tag, never the monitored=1 default.
    assert all(r.monitored == 0 for r in seeded)
    # And none of them surface on the board.
    assert "preseed-a" not in {r.slug for r in dash.latest_rows(db)}


def test_unmonitored_rows_are_invisible_to_the_board(db):
    _snapshot(db, "preseed-board", 1e6, monitored=1)
    _snapshot(db, "preseed-a", 9e9, monitored=0)  # a pre-seeded CEX total
    db.commit()

    rows = dash.latest_rows(db)
    assert {r.slug for r in rows} == {"preseed-board"}
    # A single huge unmonitored row must not leak into the aggregate total.
    stats = dash.aggregate_stats(rows, [])
    assert stats.total_tvl == 1e6
    assert stats.protocol_count == 1


def test_unmonitored_capture_does_not_keep_board_fresh(db):
    # Only an unmonitored row exists: the board has nothing *monitored*, so the
    # staleness clock reports empty (None), not the seed's fresh timestamp.
    _snapshot(db, "preseed-a", 1e9, monitored=0)
    db.commit()
    assert dash.freshness_hours(db) is None
