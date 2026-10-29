"""Unit tests for the deterministic metric primitives."""

import time

import pandas as pd
import pytest
from app.analysis import metrics


def daily_series(values: list[float], end_days_ago: int = 0) -> list[tuple[int, float]]:
    """Build a [(ts, value)] series ending `end_days_ago` days before now."""
    now = int(time.time())
    n = len(values)
    return [(now - (n - 1 - i + end_days_ago) * 86_400, v) for i, v in enumerate(values)]


class TestSeriesToFrame:
    def test_empty_series(self):
        df = metrics.series_to_frame([])
        assert df.empty

    def test_daily_fill_and_index(self):
        df = metrics.series_to_frame(daily_series([100, 110, 120]))
        assert len(df) == 3
        assert list(df["tvl"]) == [100, 110, 120]

    def test_gaps_are_forward_filled(self):
        now = int(time.time())
        series = [(now - 10 * 86_400, 100.0), (now, 150.0)]
        df = metrics.series_to_frame(series)
        assert len(df) == 11
        # days 2..10 carry the previous value before the jump
        assert df["tvl"].iloc[5] == 100.0
        assert df["tvl"].iloc[-1] == 150.0

    def test_duplicate_dates_take_max(self):
        now = int(time.time())
        series = [(now, 100.0), (now + 60, 105.0)]
        df = metrics.series_to_frame(series)
        assert df["tvl"].iloc[-1] == 105.0


class TestPctChange:
    def test_known_value(self):
        df = metrics.series_to_frame(daily_series([100, 100, 100, 100, 100, 100, 100, 120]))
        chg = metrics.pct_change(df, 7)
        assert chg == pytest.approx(20.0)

    def test_short_series_returns_none(self):
        df = metrics.series_to_frame(daily_series([100]))
        assert metrics.pct_change(df, 7) is None

    def test_zero_baseline_returns_none(self):
        df = pd.DataFrame({"tvl": [0.0, 50.0]}, index=pd.date_range("2024-01-01", periods=2))
        assert metrics.pct_change(df, 1) is None


class TestVolatility:
    def test_constant_series_has_zero_volatility(self):
        df = metrics.series_to_frame(daily_series([100] * 40))
        vol = metrics.volatility(df, 30)
        assert vol is not None
        assert vol == pytest.approx(0.0, abs=1e-9)

    def test_insufficient_history_returns_none(self):
        df = metrics.series_to_frame(daily_series([100, 101, 99]))
        assert metrics.volatility(df, 30) is None

    def test_alternating_series_volatility_sanity(self):
        values = [100, 110, 100, 110, 100, 110, 100, 110]
        df = metrics.series_to_frame(daily_series(values))
        vol = metrics.volatility(df, 30)
        # daily returns alternate ~ +10%/-9.1%; std-dev should land in a sane band
        assert 0.05 < vol < 0.15


class TestChainConcentration:
    def test_single_chain(self):
        info = metrics.chain_concentration({"Ethereum": 100.0})
        assert info["hhi"] == pytest.approx(1.0)
        assert info["top_chain"] == "Ethereum"

    def test_ignores_composite_and_non_chain_keys(self):
        info = metrics.chain_concentration(
            {
                "Ethereum": 80.0,
                "Arbitrum": 20.0,
                "Ethereum-staking": 500.0,
                "staking": 400.0,
                "pool2": 10.0,
                "borrowed": 999.0,
            }
        )
        assert info["total_tvl"] == pytest.approx(100.0)
        assert info["top_chain_share"] == pytest.approx(0.8)

    def test_empty_input(self):
        info = metrics.chain_concentration({})
        assert info["total_tvl"] == 0.0

    def test_balanced_markets_have_low_hhi(self):
        info = metrics.chain_concentration({f"c{i}": 10.0 for i in range(10)})
        assert info["hhi"] == pytest.approx(0.1)


class TestIncentiveRatio:
    def test_basic_ratio(self):
        tvl = daily_series([1000] * 10)
        staking = daily_series([300] * 10)
        assert metrics.incentive_ratio(tvl, staking) == pytest.approx(0.3)

    def test_missing_staking_returns_none(self):
        assert metrics.incentive_ratio(daily_series([100] * 5), []) is None


class TestFreshness:
    def test_fresh_data(self):
        df = metrics.series_to_frame(daily_series([100, 101]))
        assert metrics.data_freshness_days(df) == 0

    def test_stale_data(self):
        df = metrics.series_to_frame(daily_series([100, 101, 102], end_days_ago=5))
        assert metrics.data_freshness_days(df) == 5

    def test_empty(self):
        assert metrics.data_freshness_days(metrics.series_to_frame([])) is None
