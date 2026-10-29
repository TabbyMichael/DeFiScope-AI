"""Parsing tests for the fee/volume enrichment endpoints (mocked, no network)."""

import httpx
import respx
from app.clients.defillama import DefiLlamaClient

FEES = "https://fees.llama.fi"


class TestFeeRevenue:
    @respx.mock
    async def test_parses_fees_and_revenue_totals(self):
        respx.get(f"{FEES}/summary/fees/aave?dataType=dailyFees").respond(
            200, json={"total24h": 10, "total7d": 70, "total30d": 300}
        )
        respx.get(f"{FEES}/summary/fees/aave?dataType=dailyRevenue").respond(
            200, json={"total24h": 4, "total30d": 120}
        )
        async with httpx.AsyncClient() as client:
            summary = await DefiLlamaClient().get_fee_revenue(client, "aave")
        assert summary is not None
        assert (summary.fees_24h, summary.fees_7d, summary.fees_30d) == (10.0, 70.0, 300.0)
        assert (summary.revenue_24h, summary.revenue_30d) == (4.0, 120.0)

    @respx.mock
    async def test_partial_series_keeps_available_fields(self):
        # Revenue host tracked, fees host returns a null total -> that field stays None.
        respx.get(f"{FEES}/summary/fees/x?dataType=dailyFees").respond(
            200, json={"total24h": None, "total30d": 50}
        )
        respx.get(f"{FEES}/summary/fees/x?dataType=dailyRevenue").respond(404, json={"e": "nf"})
        async with httpx.AsyncClient() as client:
            summary = await DefiLlamaClient().get_fee_revenue(client, "x")
        assert summary is not None
        assert summary.fees_24h is None  # null, not coerced to 0
        assert summary.fees_30d == 50.0
        assert summary.revenue_24h is None

    @respx.mock
    async def test_degrades_to_none_when_untracked(self):
        respx.get(url__regex=r".*/summary/fees/.*").respond(404, json={"error": "not found"})
        async with httpx.AsyncClient() as client:
            assert await DefiLlamaClient().get_fee_revenue(client, "ghost") is None


class TestDexVolume:
    @respx.mock
    async def test_parses_volume_totals(self):
        respx.get(url__regex=r".*/overview/dexs/.*").respond(
            200, json={"total24h": 5000, "total7d": 35000, "total30d": 150000}
        )
        async with httpx.AsyncClient() as client:
            vol = await DefiLlamaClient().get_dex_volume(client, "uniswap-v3")
        assert vol is not None
        assert (vol.volume_24h, vol.volume_7d, vol.volume_30d) == (5000.0, 35000.0, 150000.0)

    @respx.mock
    async def test_non_dex_protocol_is_gap(self):
        respx.get(url__regex=r".*/overview/dexs/.*").respond(404, json={"error": "not found"})
        async with httpx.AsyncClient() as client:
            assert await DefiLlamaClient().get_dex_volume(client, "aave") is None


class TestStablecoinPegHistory:
    @respx.mock
    async def test_parses_price_series_per_coin(self):
        respx.get(url__regex=r".*/chart/.*").respond(
            200,
            json={
                "coins": {
                    "coingecko:dai": {
                        "symbol": "DAI",
                        "confidence": 0.99,
                        "prices": [
                            {"timestamp": 2, "price": 1.001},
                            {"timestamp": 1, "price": 0.999},
                        ],
                    }
                }
            },
        )
        async with httpx.AsyncClient() as client:
            out = await DefiLlamaClient().get_stablecoin_prices(client, ["coingecko:dai"])
        assert out == {"coingecko:dai": [(1, 0.999), (2, 1.001)]}  # sorted by ts

    @respx.mock
    async def test_degrades_to_empty_on_failure(self):
        respx.get(url__regex=r".*/chart/.*").respond(404, json={"error": "not found"})
        async with httpx.AsyncClient() as client:
            out = await DefiLlamaClient().get_stablecoin_prices(client, ["coingecko:dai"])
        assert out == {}

    async def test_no_coins_makes_no_request(self):
        async with httpx.AsyncClient() as client:
            assert await DefiLlamaClient().get_stablecoin_prices(client, []) == {}
