"""Deterministic metric calculations over TVL time series.

All functions are pure and unit-tested; the risk scorer and alert engine
build on top of these primitives so that every displayed number can be
traced back to a documented formula (see docs/methodology.md).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

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


def ratio_to_tvl(value: float | None, tvl: float | None) -> float | None:
    """Trailing ``value`` (fees, revenue or volume) as a fraction of current TVL
    - a capital-efficiency ratio. None when either side is missing or TVL is not
    positive, so an unavailable feed stays a gap rather than reading as 0."""
    if value is None or tvl is None or tvl <= 0:
        return None
    return value / tvl


def fees_tvl_ratio(fees: float | None, tvl: float | None) -> float | None:
    """Fees generated relative to TVL over the same window (see ratio_to_tvl)."""
    return ratio_to_tvl(fees, tvl)


def volume_tvl_ratio(volume: float | None, tvl: float | None) -> float | None:
    """Trading volume relative to TVL (turnover) over the same window."""
    return ratio_to_tvl(volume, tvl)


def price_normalized_tvl(
    tvl_history: list[tuple[int, float]],
    price_history: list[tuple[int, float]],
    window_days: int = 30,
) -> float | None:
    """TVL change expressed in token terms, i.e. after dividing out the token's
    own price. This decomposes a USD-TVL move into 'usage' vs 'price': if USD TVL
    rose only because the token price rose, the price-normalized change is near
    zero. Returns a percentage, or None when either series is missing/too short
    or the aligned window has no valid price points."""
    if not tvl_history or not price_history:
        return None
    tvl_df = series_to_frame(tvl_history)
    price_df = series_to_frame(price_history).rename(columns={"tvl": "price"})
    joined = tvl_df.join(price_df, how="inner")
    if len(joined) < 2:
        return None
    joined = joined.iloc[-window_days:]
    first, last = joined.iloc[0], joined.iloc[-1]
    if first["price"] <= 0 or last["price"] <= 0:
        return None
    start = first["tvl"] / first["price"]
    end = last["tvl"] / last["price"]
    if start <= 0:
        return None
    return (end - start) / start * 100.0


def peg_deviation_bps(price: float | None, target: float = 1.0) -> float | None:
    """Signed deviation of a stablecoin price from its peg, in basis points.
    ``target`` is the intended price (1.0 for a USD-pegged coin). Returns None
    for a missing price or a non-positive target so an absent feed stays a gap."""
    if price is None or target <= 0:
        return None
    return (price - target) / target * 10_000.0


def max_peg_deviation_bps(
    price_history: list[tuple[int, float]], target: float = 1.0
) -> float | None:
    """Worst absolute peg deviation over the observed window, in basis points.
    None when the series is empty or has no valid price - i.e. 'unknown', never
    read as 'on peg'."""
    devs = [
        abs(d)
        for d in (peg_deviation_bps(price, target) for _ts, price in price_history)
        if d is not None
    ]
    if not devs:
        return None
    return max(devs)


def depeg_duration(
    price_history: list[tuple[int, float]], tolerance_bps: float, target: float = 1.0
) -> int | None:
    """Count of observations that sat beyond +/- ``tolerance_bps`` of the peg.
    With a daily ``/chart`` cadence this approximates days-out-of-band. None when
    there is no valid data (a gap), 0 when the coin held its peg throughout."""
    devs = [
        d
        for d in (peg_deviation_bps(price, target) for _ts, price in price_history)
        if d is not None
    ]
    if not devs:
        return None
    return sum(1 for d in devs if abs(d) > tolerance_bps)


def data_freshness_days(df: pd.DataFrame) -> int | None:
    """Days between the latest observation and now (UTC)."""
    if df.empty:
        return None
    last = df.index.max()
    if last.tzinfo is None:
        last = last.tz_localize("UTC")
    return max(0, (datetime.now(UTC) - last).days)
