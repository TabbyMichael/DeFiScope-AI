# Research Methodology

This document defines exactly how DeFiScope AI computes every number it displays,
what each metric can and cannot establish, and where human judgment is required.
It is the contract between the dashboard and the analyst.

## Data sources

| Source | Used for | Known limitations |
|---|---|---|
| [DefiLlama](https://api.llama.fi) (`/protocols`, `/protocol/{slug}`) | TVL, TVL history, chain distribution, staking TVL, category, audit count | TVL is USD-denominated, so it conflates price movement with usage. Cross-protocol double counting (e.g. wrapped assets) is possible. Audit metadata is self-reported and coarse. |
| Curated security notes (`app/analysis/scoring.py::KNOWN_SECURITY_NOTES`) | Historical incidents (e.g. Curve's Aug 2023 Vyper exploit) | Intentionally minimal; a research prompt, not an incident database. |

All outputs carry an `as_of` date (timestamp of the latest underlying observation)
and source links. The API refuses to silently present stale data: freshness is a
first-class field and a monitoring rule.

## Metric primitives (`app/analysis/metrics.py`)

Raw DefiLlama point series are normalized to a **daily, forward-filled UTC frame**.
Duplicate intraday points are aggregated with `max` (DefiLlama issues retro
corrections). Forward-filling never fabricates values before the first observation.

- **TVL change (7d / 30d)**: `(latest - value_n_days_ago) / value_n_days_ago`.
  Returns `None` (never a guess) when history is insufficient or the baseline is zero.
- **Volatility (30d)**: standard deviation of daily TVL returns over the trailing
  30 days, requiring ≥5 observations.
- **Max drawdown (30d)**: worst peak-to-trough decline within the window.
- **Chain concentration**: Herfindahl-Hirschman Index (HHI) over per-chain TVL
  shares. DefiLlama's pseudo-chains (`staking`, `pool2`, `borrowed`, and composite
  keys like `Ethereum-staking`) are excluded — this is a common silent error in
  TVL dashboards and we filter it explicitly (and test it).
- **Incentive ratio**: latest staking/LP-rewards TVL ÷ core TVL.
- **Data freshness**: days between the last observation and now.

Every primitive is covered by unit tests (`tests/test_metrics.py`).

## Risk indicators (`app/analysis/scoring.py`)

Each indicator produces `{value, score 0–100, weight, evidence, limitation}`
where **100 = maximum risk contribution**. Scores are linear maps between a
"safe" and "risky" anchor value, clamped to [0, 100]. Anchors are documented
judgment calls, not market truth:

| Indicator | Weight | Anchor: safe → risky | What it CANNOT establish |
|---|---|---|---|
| Chain / liquidity concentration (HHI) | 0.25 | 0.15 → 0.95 | Security of the dominant chain itself; bridge risk between chains |
| TVL volatility (30d std-dev of daily returns) | 0.25 | 0.5% → 10% | Whether moves are price-driven vs usage-driven |
| TVL trend (30d change) | 0.15 | +5% → −40% | Organic vs incentive-driven flows (see below) |
| Incentive dependence (staking/core TVL) | 0.15 | 5% → 80% | Mercenary vs long-term stakers (Lido's ratio is high by design) |
| Security posture (audit count + curated notes) | 0.20 | 3+ audits → 0 audits + incident history | Coverage, recency, or post-audit upgrades. Never a safety guarantee |

**Composite score** = weighted mean over *available* indicators, renormalized so
missing data does not count as "safe". If any indicator is not computable it is
reported under `data_gaps`. Bands: `low` <30 ≤ `moderate` <50 ≤ `elevated` <70 ≤ `high`.

### The central analytical caveat

> Rising or falling TVL, by itself, proves nothing about sustainable growth or
> protocol risk. Token prices, market conditions, incentive emissions, and
> one-time whale movements all move USD TVL. DeFiScope therefore never labels a
> protocol "healthy" because TVL rose; it flags the *reason to investigate*
> (e.g. a TVL surge triggers an "verify incentive-driven" alert) and states the
> missing evidence (volume, fees, emissions schedules) in the data-gaps section
> of every brief.

## Research briefs (`app/services/briefs.py`)

Briefs are generated from the structured evidence pack only — the LLM path is
constrained to provided numbers ("never invent numbers" system instruction, JSON
schema output) and the deterministic template fallback produces the same sections
from the same evidence when no LLM is configured. `generated_by` is always
surfaced so a reader knows which engine wrote the prose. Confidence is downgraded
automatically when data gaps exist.

## Monitoring rules (`app/services/alerts.py`)

| Rule | Default threshold | Severity | Rationale |
|---|---|---|---|
| `tvl_drop` | ≤ −15% over 7d (critical at ≤ −30%) | warning/critical | Sustained outflow is the clearest exit signal in TVL data |
| `daily_shock` | ≤ −10% in 24h | critical | Overnight crashes correlate with exploits/depegs/mass exits |
| `tvl_surge` | ≥ +30% over 7d | info | Growth this fast is usually emissions-backed; verify before believing it |
| `incentive_dependence` | staking/core ≥ 0.60 | warning | Flags emission-driven value for investigation |
| `stale_data` | last observation > 2d old | warning | Upstream collection failure; protects downstream conclusions |

Alert IDs are deterministic per protocol/rule/day, so re-runs are idempotent.
Every alert embeds its triggering evidence: metric, observed value, threshold.

## What this system deliberately does NOT claim

- It does not detect wash trading or sybil activity (needs transaction-level data).
- It does not evaluate token emission schedules (not in free DefiLlama endpoints).
- It does not replace smart-contract audits or incident forensics.
- Its security-posture signal is a weak proxy that prompts manual review.

These boundaries are surfaced in the UI as `data_gaps` rather than hidden.
