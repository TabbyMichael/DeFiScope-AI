"""Protocol research orchestration: fetch -> normalize -> metrics -> risk.

Results are cached in-process for CACHE_TTL seconds so dashboard refreshes
and brief generation do not hammer the public DefiLlama API.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from app.analysis import metrics, scoring
from app.clients.defillama import DefiLlamaClient, ProtocolDetail, ProtocolSummary
from app.schemas import ChainShare, ProtocolOverview, ProtocolResearch, TvlPoint

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # DefiLlama TVL is updated hourly; 5 min cache is ample


@dataclass
class ResearchPack:
    """Everything downstream consumers (risk, briefs, alerts) need."""

    summary: ProtocolSummary | None
    detail: ProtocolDetail
    tvl_df: "object" = field(default_factory=lambda: None)
    risk: scoring.RiskAssessment | None = None

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
    def __init__(self, client: DefiLlamaClient | None = None) -> None:
        self.client = client or DefiLlamaClient()
        self._cache: dict[str, tuple[float, ResearchPack]] = {}
        self._list_cache: tuple[float, dict[str, ProtocolSummary]] | None = None

    async def _protocol_index(self, http: httpx.AsyncClient) -> dict[str, ProtocolSummary]:
        now = time.monotonic()
        if self._list_cache and now - self._list_cache[0] < CACHE_TTL_SECONDS:
            return self._list_cache[1]
        summaries = await self.client.list_protocols(http)
        index = {s.slug: s for s in summaries}
        self._list_cache = (now, index)
        return index

    async def get_pack(self, slug: str, http: httpx.AsyncClient, refresh: bool = False) -> ResearchPack:
        now = time.monotonic()
        if not refresh and slug in self._cache and now - self._cache[slug][0] < CACHE_TTL_SECONDS:
            return self._cache[slug][1]

        detail = await self.client.get_protocol(http, slug)
        index = await self._protocol_index(http)
        summary = index.get(slug)
        tvl_df = metrics.series_to_frame(detail.tvl_history)
        risk = scoring.assess(
            slug=slug,
            tvl_df=tvl_df,
            chain_tvls=detail.current_chain_tvls,
            tvl_history=detail.tvl_history,
            staking_history=detail.staking_history,
            audits=summary.audits if summary else None,
        )
        pack = ResearchPack(summary=summary, detail=detail, tvl_df=tvl_df, risk=risk)
        self._cache[slug] = (now, pack)
        return pack

    async def get_packs(self, slugs: list[str], http: httpx.AsyncClient) -> list[ResearchPack]:
        packs = []
        for slug in slugs:
            try:
                packs.append(await self.get_pack(slug, http))
            except Exception as exc:  # noqa: BLE001 - one bad slug must not sink the board
                logger.warning("Failed to load protocol %s: %s", slug, exc)
        return packs


def pack_to_overview(pack: ResearchPack) -> ProtocolOverview:
    risk = pack.risk
    chain_info = metrics.chain_concentration(pack.detail.current_chain_tvls)
    chg_7d = metrics.pct_change(pack.tvl_df, 7)
    chg_30d = metrics.pct_change(pack.tvl_df, 30)
    vol = metrics.volatility(pack.tvl_df, 30)
    inc = metrics.incentive_ratio(pack.detail.tvl_history, pack.detail.staking_history)
    return ProtocolOverview(
        slug=pack.slug,
        name=pack.detail.name,
        category=pack.summary.category if pack.summary else None,
        tvl=pack.latest_tvl,
        change_7d=round(chg_7d, 2) if chg_7d is not None else None,
        change_30d=round(chg_30d, 2) if chg_30d is not None else None,
        volatility_30d=round(vol, 4) if vol is not None else None,
        top_chain=chain_info.get("top_chain"),
        top_chain_share=round(chain_info["top_chain_share"], 4) if chain_info["total_tvl"] > 0 else None,
        incentive_ratio=round(inc, 4) if inc is not None else None,
        risk_score=risk.composite_score if risk else None,
        risk_band=risk.band if risk else "unknown",
        stale_days=metrics.data_freshness_days(pack.tvl_df),
        as_of=pack.latest_date,
    )


def pack_to_research(pack: ResearchPack, window_days: int = 180) -> ProtocolResearch:
    df = pack.tvl_df
    series = []
    if df is not None and not df.empty:
        tail = df.iloc[-window_days:]
        series = [TvlPoint(date=str(idx.date()), tvl=round(float(v), 2)) for idx, v in tail["tvl"].items()]
    chain_info = metrics.chain_concentration(pack.detail.current_chain_tvls)
    chains = [
        ChainShare(chain=chain, tvl=round(pack.detail.current_chain_tvls[chain], 2), share=round(share, 4))
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
        data_gaps=risk.data_gaps if risk else [],
        as_of=pack.latest_date or "n/a",
        sources=[
            f"https://defillama.com/protocol/{pack.slug}",
            "https://api.llama.fi",
        ],
    )
