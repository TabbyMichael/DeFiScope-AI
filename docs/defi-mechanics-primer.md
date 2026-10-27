# DeFi Mechanics Primer — What to Know Before the Interview

A compact reference for the mechanics this project touches. Each section ends
with "how DeFiScope sees it" and "what the data can't see" — the boundary
questions interviews actually probe.

## 1. Automated Market Makers (AMMs) — Uniswap et al.

**Mechanic:** Liquidity providers (LPs) deposit token pairs into a pool. Trades
price via a curve instead of an order book — constant product `x·y = k` for v2;
concentrated liquidity within manual price ranges for v3. LPs earn swap fees and
face **impermanent loss** (IL): if relative prices move, the pool's automatic
selling of the outperforming asset leaves the LP worse off than holding — only
"impermanent" until you withdraw.

**v3 nuance:** concentrated liquidity means active management; most fee revenue
accrues to a small set of professional managers, and headline TVL badly
overstates *usable* depth at any price.

**How DeFiScope sees it:** pool TVL and its trend. **What it can't see:** swap
volume, fee/IL outcomes, MEV drag, or how concentrated positions actually are.

## 2. Collateralized Lending — Aave, Compound

**Mechanic:** Suppliers earn interest from borrowers who post collateral above
the loan value. Core parameters: collateral factor (max LTV), liquidation
threshold, and penalty. If price crosses the liquidation threshold, keepers
liquidate collateral at a discount. Interest rates float with utilization.

**Real risks:** liquidation cascades in fast markets (oracles lag price),
oracle manipulation to fake collateral value, and bad-debt if liquidations can't
fill in time. Aave v3 adds e-mode (higher LTV within correlated buckets) — more
capital efficiency, tighter liquidation margins.

**How DeFiScope sees it:** TVL = supplied value. **What it can't see:**
borrow utilization, liquidation health factors, or which collateral is risky —
DefiLlama's `borrowed` series is wired into the client as the next signal.

## 3. Staking & Liquid Staking — Lido, Rocket Pool

**Mechanic:** Lock tokens to earn rewards (validator duties, security bonding).
Liquid staking tokens (stETH) represent the claim, tradable while the underlying
is bonded. Yield comes from protocol issuance + fees.

**Risks:** the token's peg (secondary market vs redemption value),
validator-client concentration, restaking layering (EigenLayer) correlating
previously independent risks.

**How DeFiScope sees it:** TVL trend + chain concentration. **What it can't
see:** the share of stakers here for yield-farming vs genuine ETH exposure.

## 4. Stablecoins — the systemic layer

**Mechanic:** Value- pegged tokens: collateralized (DAI/USDS overcollateralized),
fiat-backed (USDC), or algorithmic (failed repeatedly). DeFi's plumbing — most
lending collateral, LP halves, and settlement is stablecoin-denominated.

**Depeg channels:** collateral contagion (a depeg forces liquidations, which
crash collateral, which depegs more), reserve loss of confidence, and
bridge/mint-centralization failures. A large stable depeg is a *domino event*:
its effects propagate through every protocol holding it — a key systemic-research
angle beyond this MVP's scope (see "future work" in README).

**How DeFiScope sees it:** indirectly — protocols with heavy stablecoin exposure
show TVL shocks when depegs hit. **What it can't see:** the depeg itself
(needs per-token price series; the natural next dataset).

## 5. Incentives, emissions, and mercenary capital

**Mechanic:** Protocols mint governance tokens to bootstrap liquidity (LP farming,
staking rewards). TVL inflates while emissions are attractive and exits when
better yields appear ("mercenary capital").

**The analytical trap — the heart of this job's role:** TVL growth during an
emissions campaign *looks like adoption*. Distinguishing them requires emissions
schedules, fee/TVL ratios (real yield), and unstake behavior — none of which
headline TVL provides. DeFiScope therefore scores incentive dependence when
staking data exists, marks it a **data gap** when it doesn't, and its
`tvl_surge` alert treats suspiciously fast growth as *unverified until proven*.

## 6. Risks that TVL cannot see (know these cold)

| Risk | Mechanic | Data you'd need |
|---|---|---|
| Smart contract | Bug in newly deployed or upgradeable code | Audit reports, formal verification, upgrade history |
| Oracle | Price feeds manipulated or lagging | Chainlink/TWAP config review, Dune liquidation data |
| Governance | Hostile proposal, treasury capture | Proposal history, voting concentration |
| Counterparty | Custodian/bridge/RWA issuer failure | Exposure breakdowns |
| Liquidity | Exit depth < headline TVL (v3 concentration) | Dune pool-position queries |

## 7. Tooling one-liners

- **DefiLlama** — cross-protocol TVL/fees/stablecoin aggregates; free API; the
  backbone of this project.
- **Dune** — community SQL over decoded on-chain tables; the place for
  transaction-level truth (user counts, real volume, liquidations).
- **Etherscan / block explorers** — contract verification, holder distribution.
- **LlamaRisk / Chaos Labs** — role models for protocol risk reports: evidence,
  assumptions, severity ratings, open questions.

## 8. Interview framing cheat-sheet

- "TVL conflates price and usage — I decompose it against fee/volume data before
  drawing conclusions." (The single best line in this domain.)
- "My scoring exposes its limitations: missing data never renders as safe."
- "Surge-growth triggers verification alerts, not celebration."
- "The audit-count score is a weak proxy I surface *because* it's weak — a
  research prompt, not a conclusion."
