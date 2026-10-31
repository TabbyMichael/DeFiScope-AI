"""Protocol research orchestration: fetch -> normalize -> metrics -> risk.

Results are cached in-process for CACHE_TTL seconds so dashboard refreshes
and brief generation do not hammer the public DefiLlama API.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx
from sqlalchemy.orm import Session

from app.analysis import metrics, scoring
from app.clients.defillama import (
    DefiLlamaClient,
    DexVolumeSummary,
    FeeRevenueSummary,
    ProtocolDetail,
    ProtocolSummary,
)
from app.config import Settings, get_settings
from app.reference_data import load_stablecoin_mapping
from app.schemas import (
    ChainShare,
    OnchainActivityOut,
    ProtocolOverview,
    ProtocolResearch,
    TvlPoint,
)
from app.services import onchain as onchain_service

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # DefiLlama TVL is updated hourly; 5 min cache is ample


@dataclass
class ResearchPack:
    """Everything downstream consumers (risk, briefs, alerts) need."""

    summary: ProtocolSummary | None
    detail: ProtocolDetail
    tvl_df: object = field(default_factory=lambda: None)
    risk: scoring.RiskAssessment | None = None
    fees: FeeRevenueSummary | None = None
    volume: DexVolumeSummary | None = None
    # Stablecoin depeg watch (Increment E): symbols this protocol mints, and
    # their peg-price histories keyed by symbol. Empty dict => no tracked coin
    # or no price data (a gap, not an on-peg pass).
    minted_symbols: list[str] = field(default_factory=list)
    peg_histories: dict[str, list[tuple[int, float]]] = field(default_factory=dict)
    # On-chain activity (Dune). Populated from the DB by ``get_pack`` when a
    # session is available, never by a network call - see services/onchain.py.
    # None means "not loaded on this path", which the response layer reports as
    # an explicit gap rather than as zero activity.
    onchain: onchain_service.OnchainActivity | None = None

    @property
    def slug(self) -> str:
        return self.detail.slug

    @property
    def latest_tvl(self) -> float | None:
        if self.tvl_df is None or self.tvl_df.empty:
            return None
        return float(self.tvl_df["tvl"].iloc[-1])

    @property
    def latest_date(self) -> str | None:
        if self.tvl_df is None or self.tvl_df.empty:
            return None
        return str(self.tvl_df.index.max().date())


class ProtocolResearchService:
    def __init__(
        self, client: DefiLlamaClient | None = None, settings: Settings | None = None
    ) -> None:
        self.client = client or DefiLlamaClient()
        self.settings = settings or get_settings()
        self._cache: dict[str, tuple[float, ResearchPack]] = {}
        self._cache_max = max(1, self.settings.research_cache_max_entries)
        self._list_cache: tuple[float, dict[str, ProtocolSummary]] | None = None

    def _remember(self, slug: str, pack: ResearchPack, captured_at: float) -> None:
        """Store a pack and evict oldest entries beyond the configured cap.
        dict preserves insertion order, so ``next(iter(...))`` is the oldest.
        Combined with the TTL check on read, this bounds memory for long-lived
        processes that auto-discover the whole market."""
        self._cache[slug] = (captured_at, pack)
        while len(self._cache) > self._cache_max:
            oldest = next(iter(self._cache))
            del self._cache[oldest]

    async def _protocol_index(self, http: httpx.AsyncClient) -> dict[str, ProtocolSummary]:
        now = time.monotonic()
        if self._list_cache and now - self._list_cache[0] < CACHE_TTL_SECONDS:
            return self._list_cache[1]
        summaries = await self.client.list_protocols(http)
        index = {s.slug: s for s in summaries}
        self._list_cache = (now, index)
        return index

    async def watchlist_slugs(self, http: httpx.AsyncClient) -> list[str]:
        """Curated protocols plus the top-N-by-TVL slice of the whole DefiLlama
        directory (market-wide monitoring). If the directory listing is
        unreachable we degrade to the curated list rather than failing the
        monitoring pass."""
        curated = self.settings.protocol_slugs
        n = self.settings.market_top_n
        if n <= 0:
            return curated
        try:
            index = await self._protocol_index(http)
        except Exception as exc:  # noqa: BLE001 - discovery is best-effort
            logger.warning("Market discovery failed, tracking curated list only: %s", exc)
            return curated
        excluded = self.settings.excluded_category_set
        excluded_slugs = self.settings.excluded_slug_set
        ranked = sorted(
            (
                s
                for s in index.values()
                if s.tvl is not None
                and s.slug
                and s.slug not in excluded_slugs
                and (s.category or "") not in excluded
            ),
            key=lambda s: s.tvl or 0.0,
            reverse=True,
        )
        merged = set(curated)  # protocol_slugs is already split + stripped
        for summary in ranked[:n]:
            merged.add(summary.slug)
        # Keep curated order first so alert/row ordering stays stable.
        return curated + sorted(merged - set(curated))

    async def get_pack(
        self,
        slug: str,
        http: httpx.AsyncClient,
        refresh: bool = False,
        session: Session | None = None,
    ) -> ResearchPack:
        now = time.monotonic()
        cached = self._cache.get(slug)
        if not refresh and cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
            pack = cached[1]
            # On-chain activity is read from the DB, so keeping a cached pack's
            # block current costs one indexed query and no HTTP. That matters
            # because the HTTP cache and the observation table age at different
            # rates (5 minutes vs a day), and a stale number here would be the
            # one thing this block exists not to be.
            if session is not None:
                pack.onchain = onchain_service.load(session, slug, self.settings)
            return pack

        detail = await self.client.get_protocol(http, slug)
        index = await self._protocol_index(http)
        summary = index.get(slug)
        tvl_df = metrics.series_to_frame(detail.tvl_history)
        # Enrichment (fees / volume) is strictly best-effort: the client already
        # degrades to None on any failure, and this guard keeps a total outage on
        # those secondary hosts from sinking the core TVL research pack.
        fees: FeeRevenueSummary | None = None
        volume: DexVolumeSummary | None = None
        if self.settings.economic_data_enabled:
            try:
                fees = await self.client.get_fee_revenue(http, slug)
                volume = await self.client.get_dex_volume(http, slug)
            except Exception as exc:  # noqa: BLE001 - enrichment never breaks the pack
                logger.info("Fee/volume enrichment skipped for %s: %s", slug, exc)
        # Stablecoin depeg watch: fetch peg-price history for any stablecoin the
        # curated map says this protocol mints. Best-effort - an unreachable price
        # host leaves the indicator as a gap rather than failing the pack.
        minted_symbols: list[str] = []
        peg_histories: dict[str, list[tuple[int, float]]] = {}
        if self.settings.stablecoin_data_enabled:
            coin_map = load_stablecoin_mapping().get(slug, {})
            if coin_map:
                minted_symbols = list(coin_map)
                try:
                    by_id = await self.client.get_stablecoin_prices(
                        http, list(coin_map.values()), self.settings.depeg_window_days
                    )
                    id_to_symbol = {cid: sym for sym, cid in coin_map.items()}
                    peg_histories = {
                        id_to_symbol[cid]: series
                        for cid, series in by_id.items()
                        if cid in id_to_symbol
                    }
                except Exception as exc:  # noqa: BLE001 - depeg watch is optional
                    logger.info("Stablecoin peg enrichment skipped for %s: %s", slug, exc)
        risk = scoring.assess(
            slug=slug,
            tvl_df=tvl_df,
            chain_tvls=detail.current_chain_tvls,
            tvl_history=detail.tvl_history,
            staking_history=detail.staking_history,
            audits=summary.audits if summary else None,
            fees_30d=fees.fees_30d if fees else None,
            minted_symbols=minted_symbols,
            peg_histories=peg_histories,
        )
        pack = ResearchPack(
            summary=summary,
            detail=detail,
            tvl_df=tvl_df,
            risk=risk,
            fees=fees,
            volume=volume,
            minted_symbols=minted_symbols,
            peg_histories=peg_histories,
        )
        if session is not None:
            pack.onchain = onchain_service.load(session, slug, self.settings)
        self._remember(slug, pack, now)
        return pack

    async def get_packs(
        self, slugs: list[str], http: httpx.AsyncClient, session: Session | None = None
    ) -> list[ResearchPack]:
        """Fetch many packs concurrently (bounded by crawl_concurrency).
        A failing slug is logged and skipped - one bad entry must not sink
        the whole board."""
        sem = asyncio.Semaphore(max(1, self.settings.crawl_concurrency))

        async def one(slug: str) -> ResearchPack | None:
            async with sem:
                try:
                    return await self.get_pack(slug, http, session=session)
                except Exception as exc:  # noqa: BLE001 - resilient crawl
                    logger.warning("Failed to load protocol %s: %s", slug, exc)
                    return None

        results = await asyncio.gather(*(one(s) for s in slugs))
        return [p for p in results if p is not None]


def pack_to_overview(pack: ResearchPack) -> ProtocolOverview:
    risk = pack.risk
    chain_info = metrics.chain_concentration(pack.detail.current_chain_tvls)
    chg_7d = metrics.pct_change(pack.tvl_df, 7)
    chg_30d = metrics.pct_change(pack.tvl_df, 30)
    vol = metrics.volatility(pack.tvl_df, 30)
    inc = metrics.incentive_ratio(pack.detail.tvl_history, pack.detail.staking_history)
    tvl = pack.latest_tvl
    fees = pack.fees
    volume = pack.volume
    fees_tvl = metrics.fees_tvl_ratio(fees.fees_30d if fees else None, tvl)
    volume_tvl = metrics.volume_tvl_ratio(volume.volume_30d if volume else None, tvl)
    # Depeg watch: worst observed peg deviation across the coins this protocol
    # mints (None when it mints none or the price feed was unavailable).
    depeg_worst_bps: float | None = None
    depeg_asset: str | None = None
    for sym, hist in pack.peg_histories.items():
        d = metrics.max_peg_deviation_bps(hist)
        if d is None:
            continue
        if depeg_worst_bps is None or d > depeg_worst_bps:
            depeg_worst_bps = d
            depeg_asset = sym
    return ProtocolOverview(
        slug=pack.slug,
        name=pack.detail.name,
        category=pack.summary.category if pack.summary else None,
        tvl=tvl,
        change_7d=round(chg_7d, 2) if chg_7d is not None else None,
        change_30d=round(chg_30d, 2) if chg_30d is not None else None,
        volatility_30d=round(vol, 4) if vol is not None else None,
        top_chain=chain_info.get("top_chain"),
        top_chain_share=round(chain_info["top_chain_share"], 4)
        if chain_info["total_tvl"] > 0
        else None,
        incentive_ratio=round(inc, 4) if inc is not None else None,
        fees_1d=round(fees.fees_24h, 2) if fees and fees.fees_24h is not None else None,
        fees_30d=round(fees.fees_30d, 2) if fees and fees.fees_30d is not None else None,
        revenue_1d=round(fees.revenue_24h, 2) if fees and fees.revenue_24h is not None else None,
        volume_1d=round(volume.volume_24h, 2) if volume and volume.volume_24h is not None else None,
        fees_tvl=round(fees_tvl, 6) if fees_tvl is not None else None,
        volume_tvl=round(volume_tvl, 4) if volume_tvl is not None else None,
        depeg_worst_bps=round(depeg_worst_bps, 1) if depeg_worst_bps is not None else None,
        depeg_asset=depeg_asset,
        risk_score=risk.composite_score if risk else None,
        risk_band=risk.band if risk else "unknown",
        stale_days=metrics.data_freshness_days(pack.tvl_df),
        as_of=pack.latest_date,
    )


def _onchain_out(activity: onchain_service.OnchainActivity | None) -> OnchainActivityOut:
    """Map the service value object onto the response contract.

    ``None`` is a real possibility (a code path without a DB session), and it is
    reported as an explicit gap: the schema field is non-optional precisely so
    that "not loaded" can never be mistaken for "not measured" or for zero.
    """
    if not isinstance(activity, onchain_service.OnchainActivity):
        return OnchainActivityOut(
            status="unconfigured",
            note="On-chain metrics were not loaded for this request.",
        )
    return OnchainActivityOut(
        status=activity.status,
        as_of=activity.as_of,
        chains=activity.chains,
        missing_chains=activity.missing_chains,
        active_wallets=activity.active_wallets,
        tx_count=activity.tx_count,
        tx_volume_usd=activity.tx_volume_usd,
        returning_wallets=activity.returning_wallets,
        returning_wallet_share=activity.returning_wallet_share,
        note=activity.note,
    )


def pack_to_research(pack: ResearchPack, window_days: int = 180) -> ProtocolResearch:
    df = pack.tvl_df
    series = []
    if df is not None and not df.empty:
        tail = df.iloc[-window_days:]
        series = [
            TvlPoint(date=str(idx.date()), tvl=round(float(v), 2)) for idx, v in tail["tvl"].items()
        ]
    chain_info = metrics.chain_concentration(pack.detail.current_chain_tvls)
    chains = [
        ChainShare(
            chain=chain, tvl=round(pack.detail.current_chain_tvls[chain], 2), share=round(share, 4)
        )
        for chain, share in sorted(chain_info.get("shares", {}).items(), key=lambda kv: -kv[1])
    ]
    risk = pack.risk
    return ProtocolResearch(
        slug=pack.slug,
        name=pack.detail.name,
        category=pack.summary.category if pack.summary else None,
        url=pack.summary.url if pack.summary else None,
        overview=pack_to_overview(pack),
        tvl_series=series,
        chains=chains,
        risk=risk.to_dict() if risk else {},
        onchain=_onchain_out(pack.onchain),
        data_gaps=risk.data_gaps if risk else [],
        as_of=pack.latest_date or "n/a",
        sources=[
            f"https://defillama.com/protocol/{pack.slug}",
            "https://api.llama.fi",
        ],
    )
