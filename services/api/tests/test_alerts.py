"""Tests for alert rule evaluation."""

import time

from app.clients.defillama import ProtocolDetail, ProtocolSummary
from app.services import alerts
from app.services.protocols import ResearchPack

DAY = 86_400


def make_pack(
    tvl_values: list[float],
    staking_values: list[float] | None = None,
    end_days_ago: int = 0,
    slug: str = "test-protocol",
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
    risk = scoring.assess(slug, df, detail.current_chain_tvls, tvl_hist, staking_hist, "1")
    return ResearchPack(summary=summary, detail=detail, tvl_df=df, risk=risk)


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
