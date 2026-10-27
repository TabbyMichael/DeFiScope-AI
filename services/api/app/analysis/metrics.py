"""Deterministic metric calculations over TVL time series.

All functions are pure and unit-tested; the risk scorer and alert engine
build on top of these primitives so that every displayed number can be
traced back to a documented formula (see docs/methodology.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

SECONDS_PER_DAY = 86_400


def series_to_frame(series: list[tuple[int, float]]) -> pd.DataFrame:
    """Convert [(unix_ts, usd_value), ...] to a daily-forward-filled DataFrame
    indexed by UTC date. Duplicate timestamps are aggregated by max (DefiLlama
    occasionally emits intraday corrections)."""
    if not series:
        return pd.DataFrame(columns=["tvl"])
    df = pd.DataFrame(series, columns=["ts", "tvl"])
    df["date"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.normalize()
    df = df.groupby("date", as_index=True)["tvl"].max()
    full_range = pd.date_range(df.index.min(), df.index.max(), freq="D", tz="UTC")
    # forward-fill gaps, but never fabricate leading values
    return df.reindex(full_range).ffill().to_frame("tvl").dropna()


def pct_change(df: pd.DataFrame, days: int, column: str = "tvl") -> float | None:
    """Percentage change over the trailing `days` window. Returns None when the
    series is too short or the baseline value is ~zero."""
    if len(df) < 2:
        return None
    latest = float(df[column].iloc[-1])
    window_start = df.index.max() - pd.Timedelta(days=days)
    historical = df.loc[:window_start]
    if historical.empty:
        # series shorter than the window: use the earliest observation
        base = float(df[column].iloc[0])
        if days > len(df):
            return None
    else:
        base = float(historical[column].iloc[-1])
    if base <= 0 or math.isclose(base, 0.0):
        return None
    return (latest - base) / base * 100.0


def daily_returns(df: pd.DataFrame, column: str = "tvl") -> pd.Series:
    returns = df[column].pct_change().dropna()
    return returns.clip(-1.0, 10.0)  # guard against divide-by-tiny artifacts


def volatility(df: pd.DataFrame, window_days: int = 30, column: str = "tvl") -> float | None:
    """Standard deviation of daily TVL returns over the trailing window (not
    annualized). A coarse but transparent proxy for TVL instability."""
    returns = daily_returns(df, column)
    if len(returns) < 5:
        return None
    tail = returns.iloc[-window_days:]
    return float(tail.std(ddof=1))


def max_drawdown(df: pd.DataFrame, window_days: int = 30, column: str = "tvl") -> float | None:
    """Worst peak-to-trough decline (as a negative fraction) within the window."""
    tail = df[column].iloc[-window_days:]
    if len(tail) < 5:
        return None
    running_max = tail.cummax()
    drawdown = tail / running_max - 1.0
    return float(drawdown.min())


NON_CHAIN_KEYS = {"staking", "pool2", "borrowed", "offers", "staking-pool2"}


def chain_concentration(chain_tvls: dict[str, float]) -> dict[str, float]:
    """Herfindahl-Hirschman index over TVL by chain, ignoring DefiLlama's
    composite keys (e.g. 'Ethereum-staking') and non-chain buckets
    ('staking', 'pool2', 'borrowed'). Returns shares plus HHI in
    {0,1}: 1 = single chain, near 0 = perfectly diversified."""
    clean = {
        k: v
        for k, v in chain_tvls.items()
        if "-" not in k and k.lower() not in NON_CHAIN_KEYS and v > 0
    }
    total = sum(clean.values())
    if total <= 0:
        return {"hhi": 1.0, "top_chain_share": 1.0, "total_tvl": 0.0}
    shares = {k: v / total for k, v in clean.items()}
    top_chain = max(shares, key=shares.get)
    return {
        "hhi": sum(s * s for s in shares.values()),
        "top_chain_share": shares[top_chain],
        "top_chain": top_chain,
        "total_tvl": total,
        "shares": shares,
    }


def incentive_ratio(
    tvl_history: list[tuple[int, float]], staking_history: list[tuple[int, float]]
) -> float | None:
    """Latest staking+LP-rewards TVL relative to core TVL. High ratios suggest
    a meaningful share of value is parked for token incentives rather than
    organic protocol usage. None when staking data is unavailable."""
    if not tvl_history or not staking_history:
        return None
    core_df = series_to_frame(tvl_history)
    staking_df = series_to_frame(staking_history)
    if core_df.empty or staking_df.empty:
        return None
    core = float(core_df["tvl"].iloc[-1])
    staking = float(staking_df["tvl"].iloc[-1])
    if core <= 0:
        return None
    return staking / core


def data_freshness_days(df: pd.DataFrame) -> int | None:
    """Days between the latest observation and now (UTC)."""
    if df.empty:
        return None
    last = df.index.max()
    if last.tzinfo is None:
        last = last.tz_localize("UTC")
    return max(0, (datetime.now(timezone.utc) - last).days)
