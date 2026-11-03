"""DB-first dashboard read tests (no live network)."""

import time
from datetime import UTC

import pytest
from app.analysis import metrics, scoring
from app.clients.defillama import ProtocolDetail, ProtocolSummary
from app.db import Base, ProtocolSnapshot, SessionLocal, engine
from app.schemas import Alert
from app.security.principal import Scope
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


class TestRiskHistory:
    def _row(self, slug, date, score, band="moderate"):
        return ProtocolSnapshot(
            slug=slug,
            date=date,
            name=slug,
            tvl=100.0,
            risk_score=score,
            risk_band=band if score is not None else None,
            captured_at=_now(),
        )

    def test_excludes_unscored_backfill_rows(self, session):
        # Every other day is unscored (simulates the DefiLlama backfill).
        dates = [f"2026-01-{d:02d}" for d in range(1, 11)]
        session.add_all(
            [self._row("a", d, (40.0 + i if i % 2 == 0 else None)) for i, d in enumerate(dates)]
        )
        session.commit()
        series = dashboard.risk_history(session, "a", days=90)
        assert len(series) == 5
        assert all(p.score is not None for p in series)
        # ascending by date
        assert [p.date for p in series] == sorted(p.date for p in series)

    def test_trailing_window(self, session):
        dates = [f"2026-01-{d:02d}" for d in range(1, 41)]
        session.add_all([self._row("a", d, 10.0, band="low") for d in dates])
        session.commit()
        series = dashboard.risk_history(session, "a", days=30)
        assert len(series) == 30
        assert series[0].date == "2026-01-11"
        assert series[-1].date == dates[-1]

    def test_empty_when_no_scores(self, session):
        session.add(self._row("a", "2026-01-01", None))
        session.commit()
        assert dashboard.risk_history(session, "a") == []


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


def psnap(
    slug,
    *,
    date="2026-02-01",
    tvl=100.0,
    name=None,
    category="Lending",
    top_chain="Ethereum",
    band=None,
    risk_score=None,
    change_7d=None,
    change_30d=None,
    monitored=1,
    captured_at=None,
):
    """A fully-populated snapshot row for the paginated/summary reads."""
    return ProtocolSnapshot(
        slug=slug,
        date=date,
        name=name or slug,
        category=category,
        top_chain=top_chain,
        tvl=tvl,
        risk_band=band,
        risk_score=risk_score,
        change_7d=change_7d,
        change_30d=change_30d,
        monitored=monitored,
        captured_at=captured_at or _now(),
    )


class TestLatestRowsPaginated:
    def test_returns_latest_monitored_per_slug(self, session):
        session.add_all(
            [
                psnap("a", date="2026-01-01", tvl=1.0, risk_score=10),
                psnap("a", date="2026-02-01", tvl=500.0, risk_score=80),  # latest
                psnap("b", date="2026-02-01", tvl=300.0, risk_score=50),
                psnap("preseed", date="2026-02-01", tvl=900.0, risk_score=99, monitored=0),
            ]
        )
        session.commit()
        rows, total = dashboard.latest_rows_paginated(session, sort="risk", direction="desc")
        assert total == 2  # the pre-seed row is excluded from the board
        assert [r.slug for r in rows] == ["a", "b"]  # risk 80 > 50
        assert rows[0].tvl == 500.0  # reads the latest (2026-02-01) row, not the old one

    def test_band_filter_including_unknown(self, session):
        session.add_all(
            [
                psnap("low", band="low"),
                psnap("high", band="high"),
                psnap("nulled", band=None),
                psnap("explicit", band="unknown"),
            ]
        )
        session.commit()
        _, total_high = dashboard.latest_rows_paginated(session, band="high")
        assert total_high == 1
        unk_rows, total_unk = dashboard.latest_rows_paginated(session, band="unknown")
        assert total_unk == 2  # NULL band and the literal 'unknown' both match
        assert {r.slug for r in unk_rows} == {"nulled", "explicit"}

    def test_search_matches_name_and_slug(self, session):
        session.add_all([psnap("aave-v3", name="Aave"), psnap("uniswap", name="Uniswap")])
        session.commit()
        rows, total = dashboard.latest_rows_paginated(session, q="aave")
        assert total == 1 and rows[0].slug == "aave-v3"
        _, total_partial = dashboard.latest_rows_paginated(session, q="swap")
        assert total_partial == 1  # substring of the slug/name

    def test_search_escapes_like_wildcards(self, session):
        session.add_all([psnap("percent", name="100%pool"), psnap("plain", name="plain")])
        session.commit()
        rows, total = dashboard.latest_rows_paginated(session, q="%")
        assert total == 1 and rows[0].slug == "percent"  # literal %, not a wildcard
        _, total_us = dashboard.latest_rows_paginated(session, q="_")
        assert total_us == 0  # escaped _: no row literally contains an underscore

    def test_offset_limit_window(self, session):
        session.add_all(
            [psnap(s, risk_score=10.0 * (i + 1)) for i, s in enumerate(["a", "b", "c", "d", "e"])]
        )
        session.commit()
        page1, total = dashboard.latest_rows_paginated(
            session, sort="risk", direction="desc", offset=0, limit=2
        )
        assert total == 5
        assert [r.slug for r in page1] == ["e", "d"]  # highest risk first
        page2, _ = dashboard.latest_rows_paginated(
            session, sort="risk", direction="desc", offset=2, limit=2
        )
        assert [r.slug for r in page2] == ["c", "b"]

    def test_nulls_sort_to_far_end_either_direction(self, session):
        session.add_all([psnap("scored", risk_score=5.0), psnap("unscored", risk_score=None)])
        session.commit()
        desc, _ = dashboard.latest_rows_paginated(session, sort="risk", direction="desc")
        assert [r.slug for r in desc] == ["scored", "unscored"]
        asc, _ = dashboard.latest_rows_paginated(session, sort="risk", direction="asc")
        assert [r.slug for r in asc] == ["scored", "unscored"]  # unscored still last

    def test_scope_restricts_rows_and_total(self, session):
        session.add_all(
            [
                psnap("lend", category="Lending", tvl=100.0),
                psnap("deriv", category="Derivatives", tvl=200.0),
                psnap("nocat", category=None, tvl=300.0),
            ]
        )
        session.commit()
        rows, total = dashboard.latest_rows_paginated(
            session, scope=Scope(categories=frozenset({"Lending"}))
        )
        # Derivatives is out of scope AND the NULL-category row is denied (unknown
        # never passes a restriction) - exactly what the Python board predicate does.
        assert total == 1 and rows[0].slug == "lend"


class TestBoardSummary:
    def test_aggregates_the_whole_scoped_board(self, session):
        session.add_all(
            [
                psnap("hi", date="2026-02-01", tvl=300.0, band="high", change_7d=-20, name="Hi"),
                psnap("lo", date="2026-01-31", tvl=700.0, band="low", change_7d=15, name="Lo"),
                psnap("preseed", tvl=9999.0, band="high", monitored=0),  # excluded
            ]
        )
        session.commit()
        alert_list = [
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
        stats, as_of = dashboard.board_summary(session, alerts=alert_list)
        assert stats.protocol_count == 2  # pre-seed excluded
        assert stats.total_tvl == 1000
        assert stats.by_band == {"high": 1, "low": 1}
        assert stats.top_gainer.slug == "lo"
        assert stats.top_loser.slug == "hi"
        assert stats.active_critical == 1
        assert stats.active_warning == 1
        assert as_of == "2026-02-01"  # freshest observation date across the board

    def test_summary_honors_scope(self, session):
        session.add_all(
            [
                psnap("lend", category="Lending", tvl=100.0, band="low"),
                psnap("deriv", category="Derivatives", tvl=200.0, band="high"),
            ]
        )
        session.commit()
        stats, _ = dashboard.board_summary(
            session, scope=Scope(categories=frozenset({"Derivatives"}))
        )
        assert stats.protocol_count == 1
        assert stats.total_tvl == 200


class TestDashboardPreviewCap:
    async def test_protocols_capped_but_stats_span_full_board(self, session, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "board_preview_size", 3)
        session.add_all(
            [psnap(f"p{i}", tvl=1000.0 - i, band="low", risk_score=10.0) for i in range(10)]
        )
        session.commit()
        resp = await dashboard.get_dashboard(svc=None, http=None, session=session)
        # The inline preview is capped, but the aggregate count spans the full set.
        assert resp.stats.protocol_count == 10
        assert len(resp.protocols) == 3
        # Rows arrive ordered by TVL desc, so the biggest names lead the preview.
        assert resp.protocols[0].tvl == 1000.0
