"""Explainable protocol risk scoring.

Every indicator produces a RiskIndicator with:
  - value:      the raw computed metric
  - score:      0-100 where 100 = maximum risk contribution
  - evidence:   human-readable description of what the number means
  - limitation: what the metric CANNOT establish

The composite score is a weighted mean of available indicators. Indicators
with missing data are excluded from the average and surfaced as data gaps,
so the output never silently treats "unknown" as "safe".
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import pandas as pd

from app.analysis import metrics


@dataclass
class RiskIndicator:
    key: str
    label: str
    value: float | None
    score: float | None  # 0 (safe) - 100 (risky); None = not computable
    weight: float
    evidence: str
    limitation: str


@dataclass
class RiskAssessment:
    slug: str
    composite_score: float | None
    band: str  # low | moderate | elevated | high | unknown
    indicators: list[RiskIndicator] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _linear_score(value: float, safe_at: float, risky_at: float) -> float:
    """Map value linearly onto 0-100 between safe_at and risky_at, clamped.
    Supports inverted ranges (safe_at > risky_at)."""
    if math.isclose(safe_at, risky_at):
        return 50.0
    raw = (value - safe_at) / (risky_at - safe_at) * 100.0
    return max(0.0, min(100.0, raw))


# Known security events / structural notes. Deliberately minimal and sourced;
# treat as research prompts, not a comprehensive incident database.
KNOWN_SECURITY_NOTES: dict[str, str] = {
    "aave-v3": "Multiple audits (2022-2023); no major Aave-v3 exploit to date. "
    "Reserve factor / liquidation mechanics warrant separate review.",
    "uniswap-v3": "Core contracts audited and formally verified; prior v2/v3 issues "
    "were addressed pre-launch. LP concentration risk is economic, not code.",
    "lido": "Staked ETH withdrawals introduced 2023; oracle centralization and "
    "curator set are known trust assumptions.",
    "curve-dex": "Vyper compiler bug exploited August 2023 (~$73M across pools); "
    "reposited and audited since. Historical event - verify current mitigations.",
    "compound-v3": "Audited pre-launch (2023); novel single-market Comet design "
    "concentrates oracle dependency on Chainlink.",
    "makerdao": "DAO system (Vaults/DSR) migrated to the Sky protocol in 2024-25; "
    "historically strong audit record. Legacy TVL may be split across "
    "makerdao/sky listings - verify which entity is measured.",
    "sky": "Successor to the MakerDAO stablecoin system (USDS/sUSDS, 2024 migration); "
    "SKY Token Governance introduced 'guardian' modules - additional "
    "administrative trust surface. Audited; monitor governance centralization.",
    "rocket-pool": "Multiple audits; minipool operator model decentralizes custody. "
    "Native fees / Saturn upgrades are recent - confirm audit coverage "
    "of current contract versions.",
    "ether.fi": "Liquid restaking wrapper; weETH redemption relies on EigenLayer "
    "withdrawal mechanics. Audited, but restaking adds EigenLayer/pod "
    "chain trust assumptions on top of Lido-style staking risk.",
    "pancakeswap": "Long-running BSC AMM; legacy V2 router exploited Sep 2023 (~$3M, "
    "funds returned). Core forks Uniswap designs; verify current "
    "deployment audit coverage per chain.",
    "balancer": "Audited; 2021 imBTC pool incident was an oracle-manipulation vector "
    "since mitigated. StablePools rely on oracle price bands - review "
    "per-pool trust assumptions.",
    "sushi": "Fork of Uniswap with long history; 2023 exploit of legacy Moola market "
    "on BSC. Multi-fork codebase means audit coverage varies per deployment.",
    "jupiter": "Solana aggregator; May 2024 'migrate' access-control bug drained "
    "~$2.4M (funds returned). Aggregation routes depend on underlying "
    "venues' security.",
    "morpho": "Audited; vaults delegate curation to independent curators, so security "
    "posture varies per vault/market rather than being protocol-wide.",
    "fluid": "Newer composite protocol (DEX + lending + stablecoin in one contract); "
    "audited by multiple firms but shorter live-time in production - treat "
    "battle-testing evidence as limited.",
    "pendle": "Audited; PT/YT markets add oracle and expiry-mechanics complexity - "
    "rate volatility is economic exposure, not code failure.",
}


def score_liquidity_concentration(chain_shares: dict[str, float]) -> RiskIndicator:
    hhi_info = metrics.chain_concentration(chain_shares)
    hhi = hhi_info["hhi"]
    top = hhi_info.get("top_chain_share")
    top_chain = hhi_info.get("top_chain", "n/a")
    if not chain_shares or hhi_info["total_tvl"] <= 0:
        return RiskIndicator(
            key="liquidity_concentration",
            label="Chain / liquidity concentration",
            value=None,
            score=None,
            weight=0.25,
            evidence="No per-chain TVL breakdown available.",
            limitation="Cannot assess concentration without chain data.",
        )
    score = _linear_score(hhi, 0.15, 0.95)
    return RiskIndicator(
        key="liquidity_concentration",
        label="Chain / liquidity concentration",
        value=round(hhi, 3),
        score=round(score, 1),
        weight=0.25,
        evidence=(
            f"TVL HHI across chains = {hhi:.2f}; largest chain ({top_chain}) holds "
            f"{top * 100:.1f}% of protocol TVL."
        ),
        limitation=(
            "Chain concentration is a proxy for shared-infrastructure failure risk; "
            "it says nothing about the security of the dominant chain itself."
        ),
    )


def score_tvl_volatility(df: pd.DataFrame) -> RiskIndicator:
    vol = metrics.volatility(df, window_days=30)
    dd = metrics.max_drawdown(df, window_days=30)
    if vol is None:
        return RiskIndicator(
            key="tvl_volatility",
            label="TVL volatility (30d)",
            value=None,
            score=None,
            weight=0.25,
            evidence="Fewer than 5 daily observations - volatility not computable.",
            limitation="Insufficient history.",
        )
    score = _linear_score(vol, 0.005, 0.10)
    dd_txt = f"; worst 30d drawdown {dd * 100:.1f}%" if dd is not None else ""
    return RiskIndicator(
        key="tvl_volatility",
        label="TVL volatility (30d)",
        value=round(vol, 4),
        score=round(score, 1),
        weight=0.25,
        evidence=(f"Std-dev of daily TVL changes over the last 30d = {vol * 100:.2f}%{dd_txt}."),
        limitation=(
            "TVL moves are price-sensitive: USD TVL can fall purely from token price "
            "declines with no change in on-chain usage."
        ),
    )


def score_tvl_trend(df: pd.DataFrame) -> RiskIndicator:
    chg_7d = metrics.pct_change(df, 7)
    chg_30d = metrics.pct_change(df, 30)
    if chg_7d is None or chg_30d is None:
        return RiskIndicator(
            key="tvl_trend",
            label="TVL trend (7d / 30d)",
            value=None,
            score=None,
            weight=0.15,
            evidence="Trend windows not covered by the available history.",
            limitation="Insufficient history.",
        )
    # Treat sustained contraction as the risk signal; growth is not automatically safe.
    score = _linear_score(chg_30d, 5.0, -40.0)
    return RiskIndicator(
        key="tvl_trend",
        label="TVL trend (7d / 30d)",
        value=round(chg_30d, 2),
        score=round(score, 1),
        weight=0.15,
        evidence=f"TVL change: 7d {chg_7d:+.1f}%, 30d {chg_30d:+.1f}%.",
        limitation=(
            "Rising or falling TVL alone cannot distinguish organic growth from "
            "incentive-driven deposits, or decline from exit from price effects."
        ),
    )


def score_incentive_dependence(
    tvl_history: list[tuple[int, float]], staking_history: list[tuple[int, float]]
) -> RiskIndicator:
    ratio = metrics.incentive_ratio(tvl_history, staking_history)
    if ratio is None:
        return RiskIndicator(
            key="incentive_dependence",
            label="Incentive / staking dependence",
            value=None,
            score=None,
            weight=0.15,
            evidence="DefiLlama reports no staking TVL series for this protocol.",
            limitation=(
                "Absence of a staking series does not prove absence of emissions-driven "
                "activity; fee/EMAP data would be required."
            ),
        )
    score = _linear_score(ratio, 0.05, 0.80)
    return RiskIndicator(
        key="incentive_dependence",
        label="Incentive / staking dependence",
        value=round(ratio, 3),
        score=round(score, 1),
        weight=0.15,
        evidence=f"Staking/LP-rewards TVL is {ratio * 100:.1f}% of core TVL.",
        limitation=(
            "Staking TVL includes legitimate long-term stakers (e.g. Lido); the ratio "
            "flags dependence for investigation, not mercenary capital."
        ),
    )


def score_security_posture(slug: str, audits: str | None) -> RiskIndicator:
    note = KNOWN_SECURITY_NOTES.get(slug)
    n_audits: int | None = None
    if audits is not None:
        try:
            n_audits = int(float(audits))
        except ValueError:
            n_audits = None
    if n_audits is None and note is None:
        return RiskIndicator(
            key="security_posture",
            label="Security posture (audits & history)",
            value=None,
            score=None,
            weight=0.20,
            evidence="No audit count or curated security note available.",
            limitation="Manual review of audit reports and incident history required.",
        )
    base = 60.0 if n_audits == 0 else max(10.0, 55.0 - 10.0 * (n_audits or 0))
    if note and ("exploited" in note or "hack" in note.lower()):
        base = max(base, 65.0)
    parts = []
    if n_audits is not None:
        parts.append(f"{n_audits} audit(s) recorded on DefiLlama")
    if note:
        parts.append(f"note: {note}")
    return RiskIndicator(
        key="security_posture",
        label="Security posture (audits & history)",
        value=n_audits,
        score=round(base, 1),
        weight=0.20,
        evidence="; ".join(parts),
        limitation=(
            "Audit counts are a weak signal: they say nothing about coverage, recency, "
            "or upgrades since the last audit. Formal verification and bug bounties are "
            "not captured. This indicator is a prompt for manual contract review."
        ),
    )


def assess(
    slug: str,
    tvl_df: pd.DataFrame,
    chain_tvls: dict[str, float],
    tvl_history: list[tuple[int, float]],
    staking_history: list[tuple[int, float]],
    audits: str | None = None,
) -> RiskAssessment:
    indicators = [
        score_liquidity_concentration(chain_tvls),
        score_tvl_volatility(tvl_df),
        score_tvl_trend(tvl_df),
        score_incentive_dependence(tvl_history, staking_history),
        score_security_posture(slug, audits),
    ]
    scored = [i for i in indicators if i.score is not None]
    gaps = [i.key for i in indicators if i.score is None]
    if not scored:
        return RiskAssessment(
            slug=slug, composite_score=None, band="unknown", indicators=indicators, data_gaps=gaps
        )
    total_w = sum(i.weight for i in scored)
    composite = sum(i.score * i.weight for i in scored) / total_w
    band = (
        "low"
        if composite < 30
        else "moderate"
        if composite < 50
        else "elevated"
        if composite < 70
        else "high"
    )
    return RiskAssessment(
        slug=slug,
        composite_score=round(composite, 1),
        band=band,
        indicators=indicators,
        data_gaps=gaps,
    )
