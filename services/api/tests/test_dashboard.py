"""DB-first dashboard read tests (no live network)."""

import time
from datetime import UTC

import pytest
from app.analysis import metrics, scoring
from app.clients.defillama import ProtocolDetail, ProtocolSummary
from app.db import Base, ProtocolSnapshot, SessionLocal, engine
from app.schemas import Alert
from app.services import alerts, dashboard

DAY = 86_400


@pytest.fixture()
def session():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def make_pack(values, slug="p1", name="P One", category="Lending") -> "alerts.ResearchPack":
    now = int(time.time())
    n = len(values)
    hist = [(now - (n - 1 - i) * DAY, v) for i, v in enumerate(values)]
    detail = ProtocolDetail(
        slug=slug,
        name=name,
        current_chain_tvls={"Ethereum": values[-1]},
        tvl_history=hist,
        staking_history=[],
        borrowed_history=[],
    )
    summary = ProtocolSummary(slug=slug, name=name, category=category, tvl=values[-1])
    df = metrics.series_to_frame(hist)
    risk = scoring.assess(slug, df, {"Ethereum": values[-1]}, hist, [], "1")
    return alerts.ResearchPack(summary=summary, detail=detail, tvl_df=df, risk=risk)


def snap(slug, date, tvl, name=None, band=None, change_7d=None, captured_at=None):
    return ProtocolSnapshot(
        slug=slug,
        date=date,
        name=name or slug,
        category="Lending",
        tvl=tvl,
        change_7d=change_7d,
        risk_band=band,
        captured_at=captured_at or _now(),
    )


def _now():
    from datetime import datetime

    return datetime.now(UTC)


class TestBackfillHistory:
    def test_seeds_full_history_minus_latest(self, session):
        pack = make_pack([1000.0 + i for i in range(40)])
        alerts.backfill_history(session, pack)
        rows = session.query(ProtocolSnapshot).filter_by(slug="p1").all()
        # latest date is intentionally left to persist_snapshots (rich row)
        assert len(rows) == 39
        assert all(r.risk_band is None for r in rows)

    def test_idempotent_when_rows_exist(self, session):
        pack = make_pack([1000.0 + i for i in range(20)])
        alerts.backfill_history(session, pack)
        first = session.query(ProtocolSnapshot).count()
        alerts.backfill_history(session, pack)
        assert session.query(ProtocolSnapshot).count() == first


class TestLatestRows:
    def test_returns_newest_snapshot_per_slug(self, session):
        session.add_all(
            [
                snap("a", "2026-01-01", 100),
                snap("a", "2026-02-01", 200),
                snap("b", "2026-01-15", 50),
            ]
        )
        session.commit()
        rows = {r.slug: r for r in dashboard.latest_rows(session)}
        assert set(rows) == {"a", "b"}
        assert rows["a"].date == "2026-02-01"
        assert rows["a"].tvl == 200


class TestAggregateStats:
    def test_totals_bands_and_movers(self, session):
        rows = [
            snap("hi", "2026-02-01", 300, band="high", change_7d=-20),
            snap("lo", "2026-02-01", 700, band="low", change_7d=15),
        ]
        alerts_list = [
            Alert(
                id="1",
                slug="hi",
                protocol="hi",
                rule="tvl_drop",
                severity="critical",
                message="",
                evidence={},
                triggered_at="2026-02-01",
            ),
            Alert(
                id="2",
                slug="lo",
                protocol="lo",
                rule="tvl_surge",
                severity="warning",
                message="",
                evidence={},
                triggered_at="2026-02-01",
            ),
        ]
        stats = dashboard.aggregate_stats(rows, alerts_list)
        assert stats.total_tvl == 1000
        assert stats.protocol_count == 2
        assert stats.by_band == {"high": 1, "low": 1}
        assert stats.active_critical == 1
        assert stats.active_warning == 1
        assert stats.top_gainer.slug == "lo"
        assert stats.top_loser.slug == "hi"


class TestHistory:
    def test_trailing_window_ascending(self, session):
        dates = [f"2026-01-{d:02d}" for d in range(1, 41)]
        session.add_all([snap("a", d, i) for i, d in enumerate(dates)])
        session.commit()
        series = dashboard.history(session, "a", days=30)
        assert len(series) == 30
        assert series[0].date == "2026-01-11"  # oldest of trailing 30
        assert series[-1].date == dates[-1]


class TestDashboardFallback:
    async def test_empty_db_triggers_monitor_then_reads_db(self, session, monkeypatch):
        calls = {"n": 0}

        async def fake_run_monitor(svc, http, sess):
            calls["n"] += 1
            sess.add(snap("a", "2026-02-01", 500, band="low", change_7d=3))
            sess.commit()
            return []

        monkeypatch.setattr(alerts, "run_monitor", fake_run_monitor)
        resp = await dashboard.get_dashboard(svc=None, http=None, session=session)
        assert calls["n"] == 1
        assert resp.stats.protocol_count == 1
        assert resp.protocols[0].slug == "a"
        assert resp.protocols[0].source == "db"

    async def test_fresh_db_skips_monitor(self, session, monkeypatch):
        session.add(snap("a", "2026-02-01", 500, band="low", change_7d=3))
        session.commit()

        async def boom(*a, **k):
            raise AssertionError("run_monitor should not be called when DB is fresh")

        monkeypatch.setattr(alerts, "run_monitor", boom)
        resp = await dashboard.get_dashboard(svc=None, http=None, session=session)
        assert resp.stats.protocol_count == 1
