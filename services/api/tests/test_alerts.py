"""Tests for alert rule evaluation."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from app.clients.defillama import ProtocolDetail, ProtocolSummary
from app.config import get_settings
from app.db import Base, ProtocolCatalog, ProtocolSnapshot, SessionLocal, engine
from app.services import alerts
from app.services.protocols import ResearchPack

DAY = 86_400


def make_pack(
    tvl_values: list[float],
    staking_values: list[float] | None = None,
    end_days_ago: int = 0,
    slug: str = "test-protocol",
    minted_symbols: list[str] | None = None,
    peg_histories: dict[str, list[tuple[int, float]]] | None = None,
) -> ResearchPack:
    now = int(time.time())
    n = len(tvl_values)
    tvl_hist = [(now - (n - 1 - i + end_days_ago) * DAY, v) for i, v in enumerate(tvl_values)]
    staking_hist = []
    if staking_values:
        m = len(staking_values)
        staking_hist = [
            (now - (m - 1 - i + end_days_ago) * DAY, v) for i, v in enumerate(staking_values)
        ]
    detail = ProtocolDetail(
        slug=slug,
        name="Test Protocol",
        current_chain_tvls={"Ethereum": tvl_values[-1]},
        tvl_history=tvl_hist,
        staking_history=staking_hist,
        borrowed_history=[],
    )
    summary = ProtocolSummary(slug=slug, name="Test Protocol", category="Test", tvl=tvl_values[-1])
    from app.analysis import metrics, scoring

    df = metrics.series_to_frame(tvl_hist)
    risk = scoring.assess(
        slug,
        df,
        detail.current_chain_tvls,
        tvl_hist,
        staking_hist,
        "1",
        minted_symbols=minted_symbols or [],
        peg_histories=peg_histories or {},
    )
    return ResearchPack(
        summary=summary,
        detail=detail,
        tvl_df=df,
        risk=risk,
        minted_symbols=minted_symbols or [],
        peg_histories=peg_histories or {},
    )


def price_series(values: list[float]) -> list[tuple[int, float]]:
    now = int(time.time())
    n = len(values)
    return [(now - (n - 1 - i) * DAY, v) for i, v in enumerate(values)]


class TestTvlDrop:
    def test_sharp_7d_drop_triggers_warning(self):
        # drop occurs inside the 7d lookback: -22% vs baseline 7 days ago
        pack = make_pack([1000.0] * 25 + [780.0])
        triggered = [a for a in alerts.evaluate_pack(pack) if a.rule == "tvl_drop"]
        assert len(triggered) == 1
        assert triggered[0].severity == "warning"
        assert triggered[0].evidence["observed"] <= -15

    def test_collapse_below_double_threshold_is_critical(self):
        pack = make_pack([1000.0] * 25 + [600.0])  # -40% => 2x the -15% threshold
        triggered = [a for a in alerts.evaluate_pack(pack) if a.rule == "tvl_drop"]
        assert triggered and triggered[0].severity == "critical"

    def test_stable_tvl_triggers_nothing(self):
        pack = make_pack([1000.0] * 40)
        assert alerts.evaluate_pack(pack) == []


class TestTvlSurge:
    def test_incentive_style_surge_flagged_for_verification(self):
        pack = make_pack([1000.0] * 25 + [1400.0])  # +40% inside the 7d window
        surge = [a for a in alerts.evaluate_pack(pack) if a.rule == "tvl_surge"]
        assert len(surge) == 1
        assert surge[0].severity == "info"
        assert "incentive" in surge[0].message.lower()


class TestIncentiveDependence:
    def test_high_staking_ratio_flagged(self):
        pack = make_pack([1000.0] * 30, staking_values=[800.0] * 30)
        flagged = [a for a in alerts.evaluate_pack(pack) if a.rule == "incentive_dependence"]
        assert len(flagged) == 1
        assert flagged[0].evidence["observed"] == 0.8


class TestStaleData:
    def test_stale_series_flagged(self):
        pack = make_pack([1000.0] * 10, end_days_ago=5)
        stale = [a for a in alerts.evaluate_pack(pack) if a.rule == "stale_data"]
        assert len(stale) == 1
        assert stale[0].evidence["observed"] == 5


class TestDailyShock:
    def test_overnight_crash_is_critical(self):
        pack = make_pack([1000.0] * 30 + [850.0])
        shock = [a for a in alerts.evaluate_pack(pack) if a.rule == "daily_shock"]
        assert len(shock) == 1
        assert shock[0].severity == "critical"


class TestDeterminism:
    def test_ids_stable_within_same_evaluation(self):
        pack = make_pack([1000.0] * 25 + [780.0])
        first = alerts.evaluate_pack(pack)
        second = alerts.evaluate_pack(pack)
        assert {a.id for a in first} == {a.id for a in second}

    def test_alert_carries_full_evidence(self):
        pack = make_pack([1000.0] * 25 + [780.0])
        a = alerts.evaluate_pack(pack)[0]
        assert a.triggered_at
        assert {"metric", "observed", "threshold"} <= set(a.evidence)


class TestDepeg:
    def test_depegged_minted_coin_fires_critical(self):
        # DAI trading ~500 bps off peg (>= 2x the 50 bps threshold) => critical.
        pack = make_pack(
            [1000.0] * 40,
            minted_symbols=["DAI"],
            peg_histories={"DAI": price_series([0.99, 0.95, 0.98])},
        )
        depeg = [a for a in alerts.evaluate_pack(pack) if a.rule == "depeg"]
        assert len(depeg) == 1
        assert depeg[0].severity == "critical"
        assert depeg[0].evidence["asset"] == "DAI"
        assert depeg[0].evidence["observed"] >= 50

    def test_on_peg_minted_coin_is_quiet(self):
        pack = make_pack(
            [1000.0] * 40,
            minted_symbols=["DAI"],
            peg_histories={"DAI": price_series([0.9999, 1.0001, 0.9998])},
        )
        assert [a for a in alerts.evaluate_pack(pack) if a.rule == "depeg"] == []

    def test_non_issuer_is_quiet_not_silently_safe(self):
        # A protocol that mints no tracked coin produces no depeg alert (the
        # scorer surfaces it as an excluded data gap, not a low-risk pass).
        pack = make_pack([1000.0] * 40)
        assert [a for a in alerts.evaluate_pack(pack) if a.rule == "depeg"] == []


class StubService:
    """The two methods run_monitor needs, without any DefiLlama traffic."""

    def __init__(self, slugs: list[str], packs: list | None = None) -> None:
        self.slugs = slugs
        self.packs = packs or []
        self.settings = get_settings()

    async def watchlist_slugs(self, http):
        return self.slugs

    async def get_packs(self, slugs, http=None, session=None):
        return self.packs


class TestRunMonitorOnchainWiring:
    """The second provider is fetched inside the pass, and only there."""

    async def test_refresh_receives_the_discovered_watchlist(self, monkeypatch):
        seen: dict = {}

        async def fake_refresh(session, http, slugs, settings=None, client=None):
            seen["slugs"] = slugs

        monkeypatch.setattr(alerts.onchain, "refresh", fake_refresh)
        # ``batch_size = 0`` means "no bound": the pass refreshes the whole
        # discovered watchlist at once (the pre-market-wide behaviour), so
        # on-chain work must cover exactly those slugs. The bounded round-robin
        # slicing itself is covered in ``TestNextRefreshSlugs``.
        monkeypatch.setattr(get_settings(), "monitor_refresh_batch_size", 0)
        db = SessionLocal()
        try:
            await alerts.run_monitor(StubService(["aave-v3", "lido"]), object(), db)
        finally:
            db.close()

        # Discovery happens first, so on-chain work covers exactly the protocols
        # that will be packed in this pass.
        assert seen["slugs"] == ["aave-v3", "lido"]

    async def test_a_dune_outage_does_not_fail_the_pass(self, monkeypatch):
        async def exploding_refresh(*args, **kwargs):
            raise RuntimeError("dune is down")

        monkeypatch.setattr(alerts.onchain, "refresh", exploding_refresh)
        db = SessionLocal()
        try:
            assert await alerts.run_monitor(StubService(["aave-v3"]), object(), db) == []
        finally:
            db.close()

    async def test_disabled_onchain_builds_no_client(self, monkeypatch):
        class Boom:
            def __init__(self, *args, **kwargs):  # pragma: no cover - asserted
                raise AssertionError("no Dune client may be built when disabled")

        monkeypatch.setattr(alerts.onchain, "DuneClient", Boom)

        settings = get_settings()
        previous = settings.onchain_data_enabled
        settings.onchain_data_enabled = False
        db = SessionLocal()
        try:
            await alerts.run_monitor(StubService(["aave-v3"]), object(), db)
        finally:
            db.close()
            settings.onchain_data_enabled = previous


class TestSnapshotWritesAreIdempotent:
    """The scheduler's 30-minute pass and the dashboard's cold hydration can
    backfill the same slug at the same moment. Each answers "any rows yet?" with
    a SELECT, both see none, and the loser used to raise IntegrityError on
    ``uq_snapshot_slug_date`` straight out of ``GET /api/dashboard``, which the
    board renders as "API unavailable". The write now goes through
    ``ON CONFLICT DO NOTHING``, so losing the race writes nothing.
    """

    def _row(self, slug: str, date: str) -> dict:
        return {
            "slug": slug,
            "date": date,
            "name": "Race Test",
            "tvl": 10.0,
            "captured_at": datetime.now(UTC),
        }

    def test_a_duplicate_write_is_ignored_not_raised(self):
        db = SessionLocal()
        try:
            alerts._insert_snapshots_ignoring_conflicts(db, [self._row("race-test", "2026-01-01")])
            db.commit()

            # The same statement again, plus one genuinely new day: the
            # duplicate has to vanish and the new row has to land.
            alerts._insert_snapshots_ignoring_conflicts(
                db,
                [
                    self._row("race-test", "2026-01-01"),
                    self._row("race-test", "2026-01-02"),
                ],
            )
            db.commit()

            dates = (
                db.query(ProtocolSnapshot.date)
                .filter(ProtocolSnapshot.slug == "race-test")
                .order_by(ProtocolSnapshot.date)
                .all()
            )
            assert [d[0] for d in dates] == ["2026-01-01", "2026-01-02"]
        finally:
            db.query(ProtocolSnapshot).filter(ProtocolSnapshot.slug == "race-test").delete()
            db.commit()
            db.close()

    def test_no_rows_sends_no_statement(self):
        # An empty VALUES list compiles to invalid SQL, so the helper must return
        # before it ever reaches the engine.
        db = SessionLocal()
        try:
            alerts._insert_snapshots_ignoring_conflicts(db, [])
        finally:
            db.close()


@pytest.fixture()
def refresh_db():
    """A clean schema for the bounded-selection tests, torn down afterwards."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(engine)


def _snap(slug, *, captured_at, monitored=1):
    return ProtocolSnapshot(
        slug=slug,
        date="2026-01-02",
        name=slug,
        tvl=1.0,
        monitored=monitored,
        captured_at=captured_at,
    )


def _cat(slug, tvl):
    # ``name`` is NOT NULL on protocol_catalog, so every seeded row needs one.
    return ProtocolCatalog(slug=slug, name=slug, tvl=tvl)


class TestNextRefreshSlugs:
    """The rolling slice a bounded pass crawls: curated core first, then a
    never-seen bootstrap by catalog TVL, then the stalest monitored rows."""

    def test_unbounded_batch_returns_whole_watchlist(self, refresh_db):
        slugs = alerts._next_refresh_slugs(refresh_db, ["a", "b", "c"], curated=["a"], batch_size=0)
        assert slugs == ["a", "b", "c"]

    def test_curated_core_is_always_prepended(self, refresh_db):
        refresh_db.add(_cat("n1", 500.0))
        refresh_db.add(_cat("n2", 400.0))
        refresh_db.commit()
        # batch_size bounds only the NON-curated slice; the curated core rides on
        # top, so a 1-protocol batch still yields curated + 1.
        res = alerts._next_refresh_slugs(
            refresh_db, ["c1", "n1", "n2"], curated=["c1"], batch_size=1
        )
        assert res == ["c1", "n1"]

    def test_never_seen_bootstraps_by_catalog_tvl_desc(self, refresh_db):
        refresh_db.add_all(
            [
                _cat("small", 10.0),
                _cat("big", 1000.0),
                _cat("mid", 100.0),
            ]
        )
        refresh_db.commit()
        res = alerts._next_refresh_slugs(
            refresh_db, ["small", "big", "mid"], curated=[], batch_size=2
        )
        assert res == ["big", "mid"]

    def test_seen_protocols_refresh_stalest_captured_at_first(self, refresh_db):
        now = datetime.now(UTC)
        refresh_db.add_all(
            [
                _snap("old", captured_at=now - timedelta(minutes=100)),
                _snap("new", captured_at=now - timedelta(minutes=10)),
            ]
        )
        refresh_db.commit()
        res = alerts._next_refresh_slugs(refresh_db, ["old", "new"], curated=[], batch_size=1)
        assert res == ["old"]

    def test_preseed_only_row_is_treated_as_never_seen(self, refresh_db):
        now = datetime.now(UTC)
        # A monitored=1 row counts as "seen" (round-robin queue); a monitored=0
        # pre-seed row is invisible to the board, so it must still be treated as
        # never-seen and bootstrapped ahead of the stale seen row.
        refresh_db.add(_snap("seen", captured_at=now, monitored=1))
        refresh_db.add(_snap("preseed", captured_at=now, monitored=0))
        refresh_db.add_all([_cat("seen", 1.0), _cat("preseed", 1.0)])
        refresh_db.commit()
        res = alerts._next_refresh_slugs(refresh_db, ["seen", "preseed"], curated=[], batch_size=1)
        assert res == ["preseed"]

    def test_curated_counts_against_batch_when_always_curated_off(self, refresh_db):
        refresh_db.add(_cat("n1", 500.0))
        refresh_db.add(_cat("n2", 400.0))
        refresh_db.commit()
        # Off: the total (curated + slice) is bounded, so curated eats a slot.
        bounded = alerts._next_refresh_slugs(
            refresh_db,
            ["c1", "n1", "n2"],
            curated=["c1"],
            batch_size=2,
            always_curated=False,
        )
        assert bounded == ["c1", "n1"]
        # On: the slice is bounded to 2 and curated is added on top (3 total).
        added = alerts._next_refresh_slugs(
            refresh_db,
            ["c1", "n1", "n2"],
            curated=["c1"],
            batch_size=2,
            always_curated=True,
        )
        assert added == ["c1", "n1", "n2"]
