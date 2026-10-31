"""Data scoping and clearance, asserted end to end through the HTTP surface.

The subtle correctness claim under test is that scoping reaches the *aggregates*
as well as the lists: a board whose total TVL is summed over protocols the
reader cannot open is a leak that no row-level filter catches.
"""

from datetime import UTC, date, datetime

import pytest
from app.db import AlertRecord, Base, ProtocolSnapshot, SessionLocal, engine
from sqlalchemy import delete

TODAY = date.today().isoformat()
NOW = datetime.now(UTC)

# Two categories and two chains, so each axis can be exercised separately.
SNAPSHOTS = [
    {
        "slug": "scope-lending-eth",
        "name": "Scope Lending ETH",
        "category": "Lending",
        "top_chain": "Ethereum",
        "tvl": 100.0,
        "risk_band": "moderate",
    },
    {
        "slug": "scope-deriv-eth",
        "name": "Scope Derivatives ETH",
        "category": "Derivatives",
        "top_chain": "Ethereum",
        "tvl": 200.0,
        "risk_band": "elevated",
    },
    {
        "slug": "scope-lending-sol",
        "name": "Scope Lending SOL",
        "category": "Lending",
        "top_chain": "Solana",
        "tvl": 50.0,
        "risk_band": "low",
    },
]

ALERTS = [
    {
        "id": "alert-scope-critical-deriv",
        "slug": "scope-deriv-eth",
        "severity": "critical",
    },
    {
        "id": "alert-scope-warning-lending",
        "slug": "scope-lending-eth",
        "severity": "warning",
    },
]


@pytest.fixture()
def scoped_board(settings_demo):
    """A fresh-captured mini board, removed afterwards.

    ``captured_at`` is now, so the dashboard's staleness check does not fire a
    live crawl - these tests must never touch the network.
    """
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        for spec in SNAPSHOTS:
            db.add(
                ProtocolSnapshot(
                    **spec,
                    date=TODAY,
                    change_7d=1.0,
                    captured_at=NOW,
                )
            )
        for spec in ALERTS:
            db.add(
                AlertRecord(
                    id=spec["id"],
                    slug=spec["slug"],
                    protocol=spec["slug"],
                    rule="daily_shock",
                    severity=spec["severity"],
                    message=f"{spec['severity']} event",
                    evidence={},
                    triggered_at=f"{TODAY}T09:00:00+00:00",
                )
            )
        db.commit()
    finally:
        db.close()

    yield

    db = SessionLocal()
    try:
        db.execute(delete(ProtocolSnapshot).where(ProtocolSnapshot.slug.like("scope-%")))
        db.execute(delete(AlertRecord).where(AlertRecord.id.like("alert-scope-%")))
        db.commit()
    finally:
        db.close()


async def _today_total(client) -> float:
    body = (await client.get("/api/dashboard")).json()
    points = {p["date"]: p["tvl"] for p in body["aggregate_history"]}
    return points.get(TODAY, 0.0)


class TestBoardScope:
    async def test_analyst_sees_only_its_categories(self, scoped_board, analyst_client):
        body = (await analyst_client.get("/api/dashboard")).json()
        slugs = {p["slug"] for p in body["protocols"]}
        assert {"scope-lending-eth", "scope-lending-sol"} <= slugs
        assert "scope-deriv-eth" not in slugs

    async def test_unrestricted_viewer_sees_every_row(self, scoped_board, viewer_client):
        body = (await viewer_client.get("/api/dashboard")).json()
        slugs = {p["slug"] for p in body["protocols"]}
        assert {s["slug"] for s in SNAPSHOTS} <= slugs

    async def test_aggregate_history_excludes_out_of_scope_protocols(
        self, scoped_board, analyst_client, admin_client
    ):
        analyst = await _today_total(analyst_client)
        admin = await _today_total(admin_client)
        # The analyst's board must not quietly include the 200 TVL it cannot open.
        assert admin - analyst == 200.0
        assert analyst >= 150.0  # both Lending rows (ETH + SOL) are in scope

    async def test_stats_count_only_visible_protocols(
        self, scoped_board, analyst_client, admin_client
    ):
        analyst = (await analyst_client.get("/api/dashboard")).json()["stats"]
        admin = (await admin_client.get("/api/dashboard")).json()["stats"]
        assert admin["protocol_count"] - analyst["protocol_count"] == 1

    async def test_scope_is_stable_across_the_detail_routes(self, scoped_board, analyst_client):
        # Visible: allowed. Same row by direct URL: still allowed.
        ok = await analyst_client.get("/api/protocols/scope-lending-eth/history")
        assert ok.status_code == 200

        denied = await analyst_client.get("/api/protocols/scope-deriv-eth/history")
        assert denied.status_code == 403
        detail = denied.json()["detail"]
        assert detail["policy"] == "scope.category_chain"
        assert detail["failed_predicate"] == "category"

        denied_risk = await analyst_client.get("/api/protocols/scope-deriv-eth/risk-history")
        assert denied_risk.status_code == 403


class TestClearanceGate:
    async def test_clearance_one_gets_the_count_but_not_the_content(
        self, scoped_board, viewer_client
    ):
        resp = await viewer_client.get("/api/alerts")
        assert resp.status_code == 200
        ids = {a["id"] for a in resp.json()}
        assert "alert-scope-critical-deriv" not in ids
        assert "alert-scope-warning-lending" in ids
        # The withheld count is reported rather than silently omitted.
        assert int(resp.headers["x-withheld-alerts"]) >= 1

    async def test_clearance_two_sees_the_critical_alert(self, scoped_board, officer_client):
        body = (await officer_client.get("/api/dashboard")).json()
        ids = {a["id"] for a in body["alerts"]}
        assert "alert-scope-critical-deriv" in ids
        assert body["withheld_alerts"] == 0

    async def test_history_endpoint_applies_the_same_gate(self, scoped_board, viewer_client):
        resp = await viewer_client.get("/api/alerts/history")
        assert resp.status_code == 200
        assert "alert-scope-critical-deriv" not in {a["id"] for a in resp.json()}
        assert int(resp.headers["x-withheld-alerts"]) >= 1

    async def test_out_of_scope_alerts_are_neither_shown_nor_withheld(
        self, scoped_board, analyst_client
    ):
        # The critical Deriv alert is invisible to the analyst because of its
        # *scope*, not its clearance - so it must not be counted as withheld.
        resp = await analyst_client.get("/api/alerts")
        ids = {a["id"] for a in resp.json()}
        assert "alert-scope-critical-deriv" not in ids
        assert int(resp.headers["x-withheld-alerts"]) == 0


class TestMonitorGate:
    async def test_a_viewer_may_not_run_the_monitor(self, scoped_board, viewer_client):
        resp = await viewer_client.post("/api/alerts/run")
        assert resp.status_code == 403
        assert resp.json()["detail"]["policy"] == "rbac"

    async def test_an_analyst_on_fresh_data_is_refused_with_a_reason(
        self, scoped_board, analyst_client
    ):
        resp = await analyst_client.post("/api/alerts/run")
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        # Which of the two monitor gates fires depends on the wall clock; both
        # are policy denials carrying the rule that refused the pass.
        assert detail["policy"].startswith("monitor.run.")
        assert detail["policy"] in {"monitor.run.freshness", "monitor.run.business_hours"}
        assert detail["reason"]
