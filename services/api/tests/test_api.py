"""API integration tests with mocked DefiLlama responses (no live network)."""

import time
from datetime import UTC, datetime

import httpx
import pytest
import respx
from app.db import Base, ProtocolSnapshot, SessionLocal, engine
from app.main import app
from app.services import alerts as alert_engine
from app.services.protocols import ProtocolResearchService

DAY = 86_400
BASE = "https://api.llama.fi"


def series(values: list[float]) -> list[dict]:
    now = int(time.time())
    n = len(values)
    return [{"date": now - (n - 1 - i) * DAY, "totalLiquidityUSD": v} for i, v in enumerate(values)]


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
        assert len(indicators) == 7
        by_key = {i["key"]: i for i in indicators}
        assert "real_yield_dependence" in by_key
        # The fees host is not stubbed in this fixture, so the indicator must be a
        # data gap (null score, listed in gaps) - never silently treated as safe.
        assert by_key["real_yield_dependence"]["score"] is None
        assert "real_yield_dependence" in data["risk"]["data_gaps"]
        # test-protocol mints no tracked stablecoin -> depeg_exposure is an
        # excluded gap (not-applicable), never a low-risk pass.
        assert "depeg_exposure" in by_key
        assert by_key["depeg_exposure"]["score"] is None
        assert "depeg_exposure" in data["risk"]["data_gaps"]
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


class TestRiskHistoryEndpoint:
    async def test_returns_scored_snapshots_only(self, api_client):
        # Seed two scored days plus one unscored backfill row for this slug.
        Base.metadata.create_all(engine)
        now = datetime.now(UTC)
        sess = SessionLocal()
        try:
            sess.add_all(
                [
                    ProtocolSnapshot(
                        slug="risk-hist",
                        date="2026-01-01",
                        name="Risk Hist",
                        tvl=1.0,
                        risk_score=35.0,
                        risk_band="moderate",
                        captured_at=now,
                    ),
                    ProtocolSnapshot(
                        slug="risk-hist",
                        date="2026-01-02",
                        name="Risk Hist",
                        tvl=1.0,
                        risk_score=61.0,
                        risk_band="elevated",
                        captured_at=now,
                    ),
                    ProtocolSnapshot(
                        slug="risk-hist",
                        date="2026-01-03",
                        name="Risk Hist",
                        tvl=1.0,
                        risk_score=None,
                        captured_at=now,
                    ),
                ]
            )
            sess.commit()
        finally:
            sess.close()

        resp = await api_client.get("/api/protocols/risk-hist/risk-history")
        assert resp.status_code == 200
        rows = resp.json()
        assert [r["date"] for r in rows] == ["2026-01-01", "2026-01-02"]  # null excluded, ascending
        assert all(r["score"] is not None for r in rows)
        assert rows[0]["band"] == "moderate"


class TestBriefsEndpoint:
    async def test_brief_falls_back_to_template_without_llm_key(self, api_client):
        resp = await api_client.get("/api/briefs/test-protocol")
        assert resp.status_code == 200
        brief = resp.json()
        assert brief["generated_by"] == "template"
        assert "Executive summary" in brief["markdown"]
        assert brief["sections"]["recommendations"]
        assert brief["as_of"]


class TestBriefExportEndpoint:
    async def test_csv_streams_attachment(self, api_client):
        resp = await api_client.get("/api/briefs/test-protocol/export?format=csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        cd = resp.headers["content-disposition"]
        assert "attachment" in cd and "test-protocol" in cd and ".csv" in cd
        assert resp.text.startswith("section,text")
        assert "executive_summary" in resp.text

    async def test_pdf_returns_pdf_bytes(self, api_client):
        resp = await api_client.get("/api/briefs/test-protocol/export?format=pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/pdf")
        assert resp.content[:4] == b"%PDF"
        assert len(resp.content) > 500

    async def test_markdown_is_the_default_format(self, api_client):
        resp = await api_client.get("/api/briefs/test-protocol/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert "Executive summary" in resp.text

    async def test_invalid_format_is_400(self, api_client):
        resp = await api_client.get("/api/briefs/test-protocol/export?format=xls")
        assert resp.status_code == 400

    async def test_unknown_protocol_is_404(self, api_client):
        resp = await api_client.get("/api/briefs/does-not-exist/export?format=csv")
        assert resp.status_code == 404


class TestAlertsEndpoints:
    async def test_get_alerts_is_db_backed_and_does_not_crawl(self, api_client, monkeypatch):
        # A live crawl here would be expensive; the GET must serve from the DB.
        async def boom(*a, **k):
            raise AssertionError("GET /api/alerts must not trigger run_monitor")

        monkeypatch.setattr(alert_engine, "run_monitor", boom)
        Base.metadata.create_all(engine)
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        sess = SessionLocal()
        try:
            sess.add(
                alert_engine.AlertRecord(
                    id="alert-seed",
                    slug="test-protocol",
                    protocol="Test Protocol",
                    rule="tvl_drop",
                    severity="critical",
                    message="seeded",
                    evidence={"metric": "tvl_change_7d_pct", "observed": -40.0},
                    triggered_at=f"{today}T00:00:00+00:00",
                )
            )
            sess.commit()
        finally:
            sess.close()

        resp = await api_client.get("/api/alerts")
        assert resp.status_code == 200
        rows = resp.json()
        assert any(a["id"] == "alert-seed" and a["severity"] == "critical" for a in rows)

    async def test_post_run_triggers_monitor_and_returns_alerts(self, api_client, monkeypatch):
        async def fake_run(svc, http, session):
            return [
                alert_engine.Alert(
                    id="alert-run",
                    slug="test-protocol",
                    protocol="Test Protocol",
                    rule="daily_shock",
                    severity="critical",
                    message="fired",
                    evidence={},
                    triggered_at=datetime.now(UTC).isoformat(),
                )
            ]

        monkeypatch.setattr(alert_engine, "run_monitor", fake_run)
        resp = await api_client.post("/api/alerts/run")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["id"] == "alert-run"
        assert rows[0]["severity"] == "critical"
