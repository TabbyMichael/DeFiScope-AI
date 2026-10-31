"""Dune client tests (mocked, no network, no API key required).

The behaviours pinned here are the ones that decide whether a number on the
research page is a measurement or a fabrication: missing columns stay ``None``,
auth failures never retry, a slow query defers instead of blocking, and an
unconfigured deployment makes no request at all.
"""

import json

import httpx
import pytest
import respx
from app.clients.dune import DuneClient, DuneError

BASE = "https://api.dune.test/api/v1"
EXECUTE = f"{BASE}/query/42/execute"
STATUS = f"{BASE}/execution/e1/status"
RESULTS = f"{BASE}/execution/e1/results"


def make_client(**overrides) -> DuneClient:
    """A client with explicit settings so no test depends on the environment."""
    kwargs: dict = {"api_key": "test-key", "base_url": BASE, "max_retries": 2, "query_id": 42}
    kwargs.update(overrides)
    client = DuneClient(**kwargs)
    client.poll_timeout_seconds = 1.0
    client.poll_interval_seconds = 0.001
    client.result_max_age_seconds = 3600
    return client


def status(state: str, finished: bool = False) -> dict:
    return {"execution_id": "e1", "state": state, "is_execution_finished": finished}


ROW = {
    "day": "2026-10-29 00:00:00.000",
    "active_wallets": 1200,
    "tx_count": 8400,
    "tx_volume_usd": 1_500_000.5,
    "returning_wallets": 640,
}


class TestRunActivityQuery:
    @respx.mock
    async def test_executes_polls_and_decodes_rows(self):
        respx.post(EXECUTE).respond(200, json={"execution_id": "e1"})
        respx.get(STATUS).mock(
            side_effect=[
                httpx.Response(200, json=status("QUERY_STATE_EXECUTING")),
                httpx.Response(200, json=status("QUERY_STATE_COMPLETED", True)),
            ]
        )
        respx.get(RESULTS).respond(200, json={"result": {"rows": [ROW]}})

        async with httpx.AsyncClient() as http:
            out = await make_client().run_activity_query(http, "ethereum", ["0xabc"], 30)

        assert out is not None
        rows, execution_id = out
        assert execution_id == "e1"
        assert len(rows) == 1
        assert rows[0].day.isoformat() == "2026-10-29"
        assert (rows[0].active_wallets, rows[0].tx_count) == (1200, 8400)
        assert rows[0].tx_volume_usd == 1_500_000.5

    @respx.mock
    async def test_query_parameters_are_sent(self):
        route = respx.post(EXECUTE).respond(200, json={"execution_id": "e1"})
        respx.get(STATUS).respond(200, json=status("QUERY_STATE_COMPLETED", True))
        respx.get(RESULTS).respond(200, json={"result": {"rows": []}})

        async with httpx.AsyncClient() as http:
            await make_client().run_activity_query(http, "bsc", ["0xdef"], 7)

        body = json.loads(route.calls[0].request.content)
        assert body["query_parameters"] == {
            "chain": "bsc",
            "addresses": ["0xdef"],
            "days": 7,
        }
        # Server-side result caching: one execution per day is the target.
        assert body["max_age"] == 3600

    @respx.mock
    async def test_poll_deadline_defers_instead_of_raising(self):
        respx.post(EXECUTE).respond(200, json={"execution_id": "e1"})
        respx.get(STATUS).respond(200, json=status("QUERY_STATE_EXECUTING"))

        client = make_client()
        client.poll_timeout_seconds = 0.02
        async with httpx.AsyncClient() as http:
            out = await client.run_activity_query(http, "ethereum", ["0xabc"], 30)

        assert out is None  # a slow query is a deferral, not a failure

    @respx.mock
    async def test_failed_execution_raises(self):
        respx.post(EXECUTE).respond(200, json={"execution_id": "e1"})
        respx.get(STATUS).respond(200, json=status("QUERY_STATE_FAILED"))

        async with httpx.AsyncClient() as http:
            with pytest.raises(DuneError, match="QUERY_STATE_FAILED"):
                await make_client().run_activity_query(http, "ethereum", ["0xabc"], 30)

    @respx.mock
    async def test_missing_result_rows_is_a_gap_not_an_empty_success(self):
        respx.post(EXECUTE).respond(200, json={"execution_id": "e1"})
        respx.get(STATUS).respond(200, json=status("QUERY_STATE_COMPLETED", True))
        respx.get(RESULTS).respond(200, json={"result": {}})

        async with httpx.AsyncClient() as http:
            assert await make_client().run_activity_query(http, "ethereum", ["0x"], 30) is None

    @respx.mock
    async def test_unconfigured_client_makes_no_request(self):
        # No key -> no HTTP call at all. respx raises on any unmocked request,
        # so a stray call here would fail loudly rather than silently succeed.
        async with httpx.AsyncClient() as http:
            assert (
                await make_client(api_key=None).run_activity_query(http, "ethereum", [], 30) is None
            )

        async with httpx.AsyncClient() as http:
            assert (
                await make_client(query_id=None).run_activity_query(http, "ethereum", [], 30)
                is None
            )


class TestTransportErrors:
    @respx.mock
    async def test_unauthorized_is_not_retried(self):
        route = respx.post(EXECUTE).respond(401, json={"error": "invalid api key"})

        async with httpx.AsyncClient() as http:
            with pytest.raises(DuneError, match="401"):
                await make_client().execute(http, {"chain": "ethereum"})

        assert route.call_count == 1

    @respx.mock
    async def test_rate_limit_is_retried_then_succeeds(self):
        route = respx.post(EXECUTE).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}, json={}),
                httpx.Response(200, json={"execution_id": "e9"}),
            ]
        )

        async with httpx.AsyncClient() as http:
            assert await make_client().execute(http, {"chain": "ethereum"}) == "e9"

        assert route.call_count == 2

    @respx.mock
    async def test_execute_without_execution_id_raises(self):
        respx.post(EXECUTE).respond(200, json={"state": "QUERY_STATE_PENDING"})

        async with httpx.AsyncClient() as http:
            with pytest.raises(DuneError, match="execution_id"):
                await make_client().execute(http, {"chain": "ethereum"})


class TestRowContract:
    def test_missing_metric_is_none_not_zero(self):
        # The single most important assertion in this file: an absent column is
        # a data gap, and a 0 would be read as "no activity".
        rows = make_client().decode_rows([{"day": "2026-10-29"}])
        assert len(rows) == 1
        assert rows[0].tx_count is None
        assert rows[0].active_wallets is None
        assert rows[0].tx_volume_usd is None
        assert rows[0].returning_wallets is None

    def test_unexpected_column_is_ignored(self):
        rows = make_client().decode_rows([{**ROW, "something_new": "x"}])
        assert rows[0].tx_count == 8400

    def test_numeric_strings_are_coerced(self):
        rows = make_client().decode_rows([{"day": "2026-10-29", "tx_count": "42"}])
        assert rows[0].tx_count == 42

    def test_undecodable_day_drops_only_that_row(self):
        rows = make_client().decode_rows(
            [{"day": "not-a-date", "tx_count": 1}, {"day": "2026-10-29", "tx_count": 2}]
        )
        assert [r.tx_count for r in rows] == [2]
