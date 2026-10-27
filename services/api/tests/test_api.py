"""API integration tests with mocked DefiLlama responses (no live network)."""

import time

import httpx
import pytest
import respx

from app.main import app
from app.services.protocols import ProtocolResearchService

DAY = 86_400
BASE = "https://api.llama.fi"


def series(values: list[float]) -> list[dict]:
    now = int(time.time())
    n = len(values)
    return [
        {"date": now - (n - 1 - i) * DAY, "totalLiquidityUSD": v}
        for i, v in enumerate(values)
    ]


PROTOCOLS_LISTING = [
    {
        "slug": "test-protocol",
        "name": "Test Protocol",
        "category": "Lending",
        "symbol": "TST",
        "chains": ["Ethereum", "Arbitrum"],
        "tvl": 1_000_000,
        "change_1d": 0.5,
        "change_7d": 3.2,
        "change_1m": 8.1,
        "audits": "3",
        "url": "https://test-protocol.example",
        "listingTimestamp": 1_600_000_000,
    }
]

PROTOCOL_DETAIL = {
    "slug": "test-protocol",
    "name": "Test Protocol",
    "currentChainTvls": {
        "Ethereum": 700_000,
        "Arbitrum": 300_000,
        "Ethereum-staking": 50_000,
        "staking": 50_000,
    },
    "tvl": series([1_000_000 * (1 + 0.001 * i) for i in range(40)]),
    "staking": series([50_000] * 40),
    "borrowed": series([10_000] * 40),
}


@pytest.fixture()
def mock_llama():
    with respx.mock(assert_all_called=False) as rsp:
        rsp.get(f"{BASE}/protocols").respond(200, json=PROTOCOLS_LISTING)
        rsp.get(f"{BASE}/protocol/test-protocol").respond(200, json=PROTOCOL_DETAIL)
        rsp.get(f"{BASE}/protocol/does-not-exist").respond(404, json={"error": "not found"})
        yield rsp


@pytest.fixture()
async def api_client(mock_llama):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # configure app state the way lifespan would, minus the scheduler
        app.state.http = httpx.AsyncClient()
        app.state.research_service = ProtocolResearchService()
        yield client
    await app.state.http.aclose()


class TestProtocolsEndpoints:
    async def test_list_returns_normalized_overviews(self, api_client):
        resp = await api_client.get("/api/protocols")
        assert resp.status_code == 200
        row = resp.json()[0]
        assert row["slug"] == "test-protocol"
        assert row["category"] == "Lending"
        assert row["risk_band"] in ("low", "moderate", "elevated", "high")
        assert row["risk_score"] is not None
        assert row["as_of"]

    async def test_detail_includes_series_chains_and_explainable_risk(self, api_client):
        resp = await api_client.get("/api/protocols/test-protocol")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tvl_series"]) == 40
        # staking pseudo-chains must not appear as chains
        chain_names = {c["chain"] for c in data["chains"]}
        assert chain_names == {"Ethereum", "Arbitrum"}
        indicators = data["risk"]["indicators"]
        assert len(indicators) == 5
        for ind in indicators:
            assert ind["evidence"] and ind["limitation"]

    async def test_unknown_protocol_404(self, api_client):
        resp = await api_client.get("/api/protocols/does-not-exist")
        assert resp.status_code == 404

    async def test_sources_and_as_of_present(self, api_client):
        resp = await api_client.get("/api/protocols/test-protocol")
        data = resp.json()
        assert any("defillama" in s for s in data["sources"])
        assert data["as_of"] != "n/a"


class TestBriefsEndpoint:
    async def test_brief_falls_back_to_template_without_llm_key(self, api_client):
        resp = await api_client.get("/api/briefs/test-protocol")
        assert resp.status_code == 200
        brief = resp.json()
        assert brief["generated_by"] == "template"
        assert "Executive summary" in brief["markdown"]
        assert brief["sections"]["recommendations"]
        assert brief["as_of"]
