"""Market-wide watchlist discovery + resilient crawl (mocked DefiLlama)."""

import asyncio
import time

import httpx
import respx
from app.config import Settings
from app.services.protocols import ProtocolResearchService

DAY = 86_400
BASE = "https://api.llama.fi"


def series(values: list[float]) -> list[dict]:
    now = int(time.time())
    n = len(values)
    return [{"date": now - (n - 1 - i) * DAY, "totalLiquidityUSD": v} for i, v in enumerate(values)]


def listing_entry(slug: str, tvl: float, category: str = "DeFi") -> dict:
    return {"slug": slug, "name": slug.title(), "category": category, "tvl": tvl}


MARKET = [
    listing_entry("alpha", 5_000_000),
    listing_entry("beta", 9_000_000),
    listing_entry("gamma", 7_000_000),
    listing_entry("delta", 1_000_000),
]

DETAIL = {
    "slug": "alpha",
    "name": "Alpha",
    "currentChainTvls": {"Ethereum": 5_000_000},
    "tvl": series([5_000_000 * (1 + 0.001 * i) for i in range(40)]),
}


def make_service(market_top_n: int = 2, curated: str = "curated-one") -> Settings:
    return Settings(
        default_protocols=curated,
        market_top_n=market_top_n,
        crawl_concurrency=4,
    )


class TestWatchlist:
    async def test_merges_curated_with_top_n_by_tvl(self):
        with respx.mock(assert_all_called=True) as rsp:
            rsp.get(f"{BASE}/protocols").respond(200, json=MARKET)
            svc = ProtocolResearchService(settings=make_service(market_top_n=2))
            async with httpx.AsyncClient() as http:
                slugs = await svc.watchlist_slugs(http)
        # curated first, then the top-2 by TVL (beta 9M, gamma 7M), deduped
        assert slugs == ["curated-one", "beta", "gamma"]

    async def test_dedupes_curated_overlap(self):
        with respx.mock(assert_all_called=True) as rsp:
            rsp.get(f"{BASE}/protocols").respond(200, json=MARKET)
            svc = ProtocolResearchService(settings=make_service(market_top_n=3, curated="beta"))
            async with httpx.AsyncClient() as http:
                slugs = await svc.watchlist_slugs(http)
        assert slugs == ["beta", "alpha", "gamma"]  # beta not duplicated

    async def test_discovery_disabled_returns_curated_only(self):
        with respx.mock(assert_all_called=False) as rsp:
            rsp.get(f"{BASE}/protocols").respond(200, json=MARKET)
            svc = ProtocolResearchService(settings=make_service(market_top_n=0))
            async with httpx.AsyncClient() as http:
                slugs = await svc.watchlist_slugs(http)
        assert slugs == ["curated-one"]

    async def test_listing_failure_degrades_to_curated(self):
        with respx.mock(assert_all_called=True) as rsp:
            rsp.get(f"{BASE}/protocols").respond(500, text="boom")
            svc = ProtocolResearchService(settings=make_service(market_top_n=5))
            async with httpx.AsyncClient() as http:
                slugs = await svc.watchlist_slugs(http)
        assert slugs == ["curated-one"]

    async def test_cex_and_bridge_categories_excluded_from_discovery(self):
        market = [
            listing_entry("whale-cex", 100_000_000, category="CEX"),
            listing_entry("mega-bridge", 90_000_000, category="Canonical Bridge"),
            listing_entry("chain-total", 80_000_000, category="Chain"),
            listing_entry("real-defi", 10_000_000, category="Liquid Staking"),
            listing_entry("second-defi", 8_000_000, category="Dexs"),
        ]
        with respx.mock(assert_all_called=True) as rsp:
            rsp.get(f"{BASE}/protocols").respond(200, json=market)
            svc = ProtocolResearchService(settings=make_service(market_top_n=2))
            async with httpx.AsyncClient() as http:
                slugs = await svc.watchlist_slugs(http)
        # custody/consensus totals skipped despite highest TVL; real DeFi ranks in
        assert slugs == ["curated-one", "real-defi", "second-defi"]

    async def test_slug_blocklist_excluded_regardless_of_category(self):
        market = [
            listing_entry("binance-staked-eth", 100_000_000, category="Liquid Staking"),
            listing_entry("real-defi", 10_000_000, category="Liquid Staking"),
            listing_entry("second-defi", 8_000_000, category="Dexs"),
        ]
        with respx.mock(assert_all_called=True) as rsp:
            rsp.get(f"{BASE}/protocols").respond(200, json=market)
            svc = ProtocolResearchService(settings=make_service(market_top_n=3))
            async with httpx.AsyncClient() as http:
                slugs = await svc.watchlist_slugs(http)
        assert slugs == ["curated-one", "real-defi", "second-defi"]


class TestConcurrentPacks:
    async def test_bad_slug_does_not_sink_the_board(self):
        with respx.mock(assert_all_called=False) as rsp:
            rsp.get(f"{BASE}/protocols").respond(200, json=MARKET)
            rsp.get(f"{BASE}/protocol/alpha").respond(200, json=DETAIL)
            rsp.get(f"{BASE}/protocol/missing").respond(404, json={"error": "nope"})
            svc = ProtocolResearchService(settings=make_service(market_top_n=0))
            async with httpx.AsyncClient() as http:
                packs = await svc.get_packs(["alpha", "missing"], http)
        assert [p.slug for p in packs] == ["alpha"]

    async def test_fetches_run_concurrently(self):
        """Each detail request sleeps 0.05s on the event loop; with concurrency
        4 the 8-slug crawl must finish well under the ~0.4s sequential time."""
        entries = [listing_entry(f"p{i}", 1000) for i in range(8)]

        async def slow_detail(request, detail):
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=detail)

        with respx.mock(assert_all_called=False) as rsp:
            rsp.get(f"{BASE}/protocols").respond(200, json=entries)
            for i in range(8):
                detail = {
                    "slug": f"p{i}",
                    "name": f"P{i}",
                    "currentChainTvls": {"Ethereum": 1000},
                    "tvl": series([1000 + j for j in range(10)]),
                }
                rsp.get(f"{BASE}/protocol/p{i}").mock(
                    side_effect=lambda request, _d=detail: slow_detail(request, _d)
                )
            svc = ProtocolResearchService(settings=make_service(market_top_n=0))
            async with httpx.AsyncClient() as http:
                start = time.monotonic()
                packs = await svc.get_packs([f"p{i}" for i in range(8)], http)
                elapsed = time.monotonic() - start
        assert len(packs) == 8
        assert elapsed < 0.35, f"crawl looks sequential: {elapsed:.2f}s"
