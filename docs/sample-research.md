# Sample Research: Aave V3 vs. Uniswap V3 — Sustainable Activity or Market Drift?

*Data as of 2026-10-27 (UTC), generated with DeFiScope AI from DefiLlama public
endpoints. This is a worked example of the analysis the platform automates —
every figure is reproducible via `GET /api/protocols/{slug}`.*

Sources:
- https://defillama.com/protocol/aave-v3
- https://defillama.com/protocol/uniswap-v3
- https://defillama.com/protocol/lido (control comparison)

---

## 1. Headline comparison

| Metric | Aave V3 (Lending) | Uniswap V3 (DEX) | Lido (Liquid staking, control) |
|---|---|---|---|
| TVL | $16.38B | $1.60B | $22.56B |
| TVL change 7d | −2.88% | −2.12% | −2.71% |
| TVL change 30d | −10.07% | −5.03% | −14.79% |
| 30d daily TVL volatility | 1.61% | 1.84% | 1.95% |
| Worst 30d drawdown | −12.0% | −8.7% | −16.4% |
| Top chain | Ethereum, 82.9% of TVL | Ethereum, 54.1% | Ethereum, ~100% |
| Composite risk score | **37.5 (moderate)** | **23.4 (low)** | **49.9 (moderate)** |

## 2. Growth: what actually happened over the window

All three protocols lost TVL over the last 30 days, and all three lost it at
roughly the same daily rate of decline with low volatility (no shock exits).
The uniformity matters: **synchronized −5% to −15% declines across unrelated
protocol categories are the signature of a market-wide price move, not
protocol-specific capital flight.** A protocol losing TVL while the market is
flat, or losing via a single-day step-down, would be a genuinely different
signal — and our alert rules (`daily_shock`, `tvl_drop`) are designed to
separate those cases.

What TVL *cannot* tell us here: whether Aave's borrow demand, Uniswap's swap
volume, or staking inflows changed at all. USD-denominated TVL conflates price
and usage. This is the single most common interpretive error in DeFi research,
and the reason this brief stops short of calling any of these protocols
"declining."

## 3. Quality of activity: what we checked and what blocked us

- **Incentive dependence: not computable from free DefiLlama endpoints for any
  of the three** (no staking/emissions series returned at analysis time). For
  Aave and Uniswap this is a genuine data gap; for Lido, staking TVL *is* the
  product, so the ratio would be near 1.0 by design — an instructive case of
  why a metric must be interpreted per category, not across it.
- **Fees/revenue cross-check (recommended next pull):** DefiLlama exposes
  separate fee/revenue endpoints. If Aave's TVL fell 10% while interest-earned
  revenue fell <5%, the decline is mostly price; if revenue fell >15%, usage is
  genuinely contracting. This one join resolves most of the ambiguity in section 2.
- **Chain mix:** Uniswap V3's TVL is spread across Ethereum (54%), Base, Arbitrum
  and others; Aave retains 83% on Ethereum. Both are defensible, but Aave's
  concentration means an Ethereum-level incident (chain halt, consensus bug,
  EIP regression) would hit ~83% of its value at once. Lido at ~100% is the
  structural extreme — by design, not by neglect.

## 4. Risk assessment (from the explainable scorer; full evidence in API payload)

**Aave V3 — 37.5 moderate.** Drivers: chain concentration (score 67.7; HHI 0.69)
and 30d trend (33.5). Security posture scored 35 from DefiLlama audit metadata
plus a curated note: multiple audits, no major v3 exploit to date. The
concentration score's limitation is explicit: it measures shared-infrastructure
dependency, not Ethereum's security.

**Uniswap V3 — 23.4 low.** The low band is *not* a safety endorsement: DEX TVL
measures only LP capital in pools. Uniswap's real risk surface — toxic order
flow, MEV extraction, IL for concentrated LPs, fee-switch governance — barely
enters TVL-based metrics. A "low risk" band from this system should be read as
"low risk *on the dimensions TVL data can see*." Flagging that boundary is the
honest deliverable.

**Lido — 49.9 moderate.** Almost entirely chain concentration (100) and trend
(44). Note what neither captures: Lido's core risks are validator-client
centralization and institutional trust assumptions — invisible to TVL data.

## 5. Recommendation for a client engagement

1. **Do not treat the 30d TVL decline as churn evidence.** Before any
   recommendation, pull fee/revenue series (DefiLlama `/summary/fees`) and ETH
   price for the same window to decompose price vs. usage effects.
2. **Aave:** investigate Ethereum-concentration mitigation (are L2 deployments
   accumulating share?) and confirm current audit coverage post-2024 upgrades.
   Monitor `daily_shock` — lending protocols show stress first as a one-day step.
3. **Uniswap:** if the engagement concerns LP participation, request on-chain
   active-position data (Dune); TVL systematically misrepresents usable liquidity
   in v3-style concentrated pools.
4. **Escalation trigger:** any `tvl_drop` ≥15% *without* a matching market-wide
   move becomes a priority investigation — that divergence is the closest TVL
   data gets to a protocol-specific exit signal.
5. **Confidence: medium.** Risk scores are computable and internally consistent,
   but incentive-dependence data is missing for all three subjects and the
   price-vs-usage decomposition is unverified pending the fee pull.

---

### Reproducibility

```bash
curl localhost:8000/api/protocols/aave-v3      # full evidence payload
curl localhost:8000/api/protocols/uniswap-v3
curl localhost:8000/api/briefs/aave-v3         # auto-generated version of this brief
```

*This document was written by hand to demonstrate the reasoning layer DeFiScope
AI supports; the platform's generated briefs follow the same structure with the
same evidence discipline.*
