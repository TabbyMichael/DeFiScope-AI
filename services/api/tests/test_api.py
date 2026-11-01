"""API integration tests with mocked DefiLlama responses (no live network)."""

import time
from datetime import UTC, datetime

import httpx
import pytest
import respx
from app.db import Base, ProtocolCatalog, ProtocolSnapshot, SessionLocal, engine
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


async def seed_protocol(slug: str) -> None:
    """Populate the DB for the DB-first detail/brief routes.

    The read path no longer crawls, so a rich payload has to be captured first.
    We run the *actual* crawl once (against the mocked DefiLlama) and persist it
    exactly as the monitoring pass would - which doubles as coverage that what a
    crawl writes is what a read renders."""
    Base.metadata.create_all(engine)
    svc = ProtocolResearchService()
    sess = SessionLocal()
    try:
        pack = await svc.get_pack(slug, app.state.http, session=sess)
        alert_engine.backfill_history(sess, pack)
        alert_engine.persist_snapshots(sess, [pack], monitored=1)
    finally:
        sess.close()


async def test_preseed_re_persist_never_demotes_a_watchlist_row(api_client):
    # Regression: a watchlist protocol's current-day row is monitored=1. The
    # background pre-seed can re-persist the SAME (slug, date) with monitored=0
    # (they overlap in the catalog), and must refresh the analysis WITHOUT
    # dropping the protocol off the board - otherwise latest_rows falls back to
    # a bare backfill history row with no risk/change ("unknown" band, no movers).
    Base.metadata.create_all(engine)
    sess = SessionLocal()
    try:
        sess.query(ProtocolSnapshot).filter_by(slug="test-protocol").delete()
        sess.commit()
        svc = ProtocolResearchService()
        pack = await svc.get_pack("test-protocol", app.state.http, session=sess)
        alert_engine.backfill_history(sess, pack)
        alert_engine.persist_snapshots(sess, [pack], monitored=1)
        date = pack.latest_date

        alert_engine.persist_snapshots(sess, [pack], monitored=0)

        row = (
            sess.query(ProtocolSnapshot)
            .filter_by(slug="test-protocol", date=date)
            .first()
        )
        assert row is not None
        assert row.monitored == 1  # never demoted by the detail pass
    finally:
        sess.query(ProtocolSnapshot).filter_by(slug="test-protocol").delete()
        sess.commit()
        sess.close()


class TestProtocolsEndpoints:
    async def test_list_is_a_paginated_catalog(self, api_client):
        # ``GET /api/protocols`` is now the DB-backed discovery catalog, not a
        # live watchlist crawl. Start from an empty catalog so the cold-start
        # metadata sync (served by the mocked /protocols) populates exactly one
        # row and the assertions below are deterministic.
        Base.metadata.create_all(engine)
        sess = SessionLocal()
        try:
            sess.query(ProtocolCatalog).delete()
            sess.commit()
        finally:
            sess.close()

        resp = await api_client.get("/api/protocols")
        assert resp.status_code == 200
        page = resp.json()
        assert page["total"] == 1
        assert page["page"] == 1
        assert page["page_size"] == 25
        assert page["pages"] == 1
        assert page["sort"] == "tvl"
        assert page["order"] == "desc"
        row = page["items"][0]
        assert row["slug"] == "test-protocol"
        assert row["name"] == "Test Protocol"
        assert row["category"] == "Lending"
        assert row["tvl"] == 1_000_000
        # Discovery never fabricates a score: an unsynced-analysis protocol
        # reports an explicit gap (null score, "unknown" band), never a zero.
        assert row["risk_score"] is None
        assert row["risk_band"] == "unknown"
        assert row["monitored"] is False

    async def test_detail_includes_series_chains_and_explainable_risk(self, api_client):
        await seed_protocol("test-protocol")
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
        await seed_protocol("test-protocol")
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
        await seed_protocol("test-protocol")
        resp = await api_client.get("/api/briefs/test-protocol")
        assert resp.status_code == 200
        brief = resp.json()
        assert brief["generated_by"] == "template"
        assert "Executive summary" in brief["markdown"]
        assert brief["sections"]["recommendations"]
        assert brief["as_of"]


class TestBriefExportEndpoint:
    async def test_csv_streams_attachment(self, api_client):
        await seed_protocol("test-protocol")
        resp = await api_client.get("/api/briefs/test-protocol/export?format=csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        cd = resp.headers["content-disposition"]
        assert "attachment" in cd and "test-protocol" in cd and ".csv" in cd
        assert resp.text.startswith("section,text")
        assert "executive_summary" in resp.text

    async def test_pdf_returns_pdf_bytes(self, api_client):
        await seed_protocol("test-protocol")
        resp = await api_client.get("/api/briefs/test-protocol/export?format=pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/pdf")
        assert resp.content[:4] == b"%PDF"
        assert len(resp.content) > 500

    async def test_markdown_is_the_default_format(self, api_client):
        await seed_protocol("test-protocol")
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
