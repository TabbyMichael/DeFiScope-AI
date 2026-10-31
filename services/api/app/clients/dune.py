"""Async client for the Dune Analytics API (second data provider).

Endpoints used (all authenticated with an ``X-Dune-API-Key`` header):
- POST /query/{query_id}/execute  - run the saved activity query, returns an id
- GET  /execution/{id}/status     - poll until the execution finishes
- GET  /execution/{id}/results    - fetch the rows

Documentation: https://docs.dune.com/api-reference

Two design rules, both mirrored from ``clients/defillama.py``:

1. **Transient failures retry, deterministic ones do not.** 429/5xx are retried
   with a capped, jittered backoff (``Retry-After`` honoured); 401/403/404 are
   raised immediately because the next attempt would fail identically.
2. **A slow query is not an error.** ``run_activity_query`` polls under a
   wall-clock deadline and returns ``None`` on expiry, so one expensive Dune
   execution can defer to the next monitoring pass instead of blocking it.

The row contract lives here too (``DuneActivityRow``): the saved query's output
is the real interface between the two systems, so it is validated on the way in
rather than trusted.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.config import get_settings

logger = logging.getLogger(__name__)

# Transient upstream statuses worth another attempt (rate limit / server blip).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Execution states. Dune reports both ``state`` and ``is_execution_finished``;
# we accept either signal so a future state string cannot hang the poll loop.
_FINISHED_STATES = {"QUERY_STATE_COMPLETED"}
_FAILED_STATES = {"QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED", "QUERY_STATE_EXPIRED"}

# The columns the saved query (data/dune/onchain_activity.sql) must return. Used
# only to raise the alarm when the query is edited in Dune's UI: a silently
# renamed column would otherwise read as "no data" forever.
_EXPECTED_COLUMNS = ("day", "active_wallets", "tx_count", "tx_volume_usd", "returning_wallets")


def _retry_delay_seconds(response: httpx.Response | None, attempt: int) -> float:
    """Seconds to wait before the next attempt.

    Honors a numeric ``Retry-After`` header when present, otherwise falls back
    to capped exponential backoff with jitter so concurrent crawls don't retry
    in lockstep."""
    if response is not None:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return max(0.0, float(raw))
            except ValueError:
                pass
    base = min(8.0, (2**attempt) * 0.5)
    return base + random.uniform(0, 0.25)


def _body(response: httpx.Response, limit: int = 200) -> str:
    """Truncated response body for an error message.

    Truncated so a verbose upstream error can't flood the logs, and safe
    because the credential travels in a header, never in the body or URL.
    """
    try:
        return (response.text or "").strip()[:limit]
    except Exception:  # noqa: BLE001 - diagnostics must never raise
        return "<unreadable body>"


class DuneError(RuntimeError):
    """Raised when Dune is unreachable, unauthorised or returns unusable data."""


@dataclass
class DuneExecution:
    """One execution's status as far as the caller cares."""

    execution_id: str
    state: str
    is_finished: bool
    is_failed: bool


class DuneActivityRow(BaseModel):
    """One row of the saved on-chain activity query.

    Every metric is optional and stays ``None`` when the query did not return
    it. That is the load-bearing decision of this module: a renamed or dropped
    Dune column must degrade to a data gap plus a log line, **never to 0** -
    zero would be read as "no activity", which is a claim we cannot make from an
    absent measurement. ``extra="ignore"`` keeps an added column harmless.
    """

    model_config = ConfigDict(extra="ignore")

    day: date
    active_wallets: int | None = None
    tx_count: int | None = None
    tx_volume_usd: float | None = None
    returning_wallets: int | None = None

    @field_validator("day", mode="before")
    @classmethod
    def _coerce_day(cls, value: object) -> object:
        """Dune returns days as ``2026-10-29 00:00:00.000`` rather than a date."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value.strip()[:10])
        return value


class DuneClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        query_id: int | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.dune_api_key
        self.base_url = (base_url or settings.dune_base_url).rstrip("/")
        self.timeout = timeout or settings.http_timeout_seconds
        self.max_retries = settings.dune_max_retries if max_retries is None else max_retries
        self.query_id = settings.dune_activity_query_id if query_id is None else query_id
        self.poll_timeout_seconds = settings.dune_poll_timeout_seconds
        self.poll_interval_seconds = settings.dune_poll_interval_seconds
        self.result_max_age_seconds = settings.dune_result_max_age_seconds

    def _headers(self) -> dict[str, str]:
        # Sent per request rather than baked into a shared AsyncClient so the
        # credential is scoped to Dune calls only: the same client also talks to
        # DefiLlama, and a stray header would leak the key to a third party.
        if not self.api_key:
            raise DuneError("No Dune API key configured")
        return {"X-Dune-API-Key": self.api_key, "Content-Type": "application/json"}

    async def _request(
        self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any
    ) -> Any:
        url = f"{self.base_url}{path}"
        attempts = max(1, self.max_retries + 1)
        for attempt in range(attempts):
            try:
                resp = await client.request(method, url, headers=self._headers(), **kwargs)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # Auth/permission/not-found are deterministic: retrying the same
                # credential or the same query id cannot succeed.
                if status in _RETRYABLE_STATUS and attempt < attempts - 1:
                    delay = _retry_delay_seconds(exc.response, attempt)
                    logger.warning(
                        "Dune %s for %s; retrying in %.2fs (attempt %d/%d)",
                        status,
                        path,
                        delay,
                        attempt + 1,
                        attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise DuneError(f"Dune error {status} for {path}: {_body(exc.response)}") from exc
            except httpx.TransportError as exc:
                if attempt < attempts - 1:
                    delay = _retry_delay_seconds(None, attempt)
                    logger.warning(
                        "Dune transport error for %s (%s); retrying in %.2fs (attempt %d/%d)",
                        path,
                        type(exc).__name__,
                        delay,
                        attempt + 1,
                        attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise DuneError(f"Dune request failed for {path}: {exc}") from exc
            except ValueError as exc:
                # Non-JSON body is not transient - retrying returns the same text.
                raise DuneError(f"Dune returned a non-JSON body for {path}: {exc}") from exc
        # Unreachable: every loop branch returns or raises. Kept for type-safety.
        raise DuneError(f"Dune request failed for {path} after {attempts} attempts")

    async def execute(
        self, client: httpx.AsyncClient, parameters: dict[str, Any], query_id: int | None = None
    ) -> str:
        """Kick off the saved query. Returns the execution id to poll."""
        qid = self.query_id if query_id is None else query_id
        if qid is None:
            raise DuneError("No Dune activity query id configured")
        body = {
            "query_parameters": parameters,
            # ``max_age`` is Dune's server-side result cache: within the window
            # an identical parameter set is served without re-executing, which
            # is what keeps a 30-minute scheduler from burning credits.
            "performance": "medium",
            "max_age": self.result_max_age_seconds,
        }
        data = await self._request(client, "POST", f"/query/{qid}/execute", json=body)
        execution_id = data.get("execution_id") if isinstance(data, dict) else None
        if not execution_id:
            raise DuneError("Dune execute returned no execution_id")
        return str(execution_id)

    async def execution(self, client: httpx.AsyncClient, execution_id: str) -> DuneExecution:
        data = await self._request(client, "GET", f"/execution/{execution_id}/status")
        if not isinstance(data, dict):
            raise DuneError(f"Unexpected status response for execution {execution_id}")
        state = str(data.get("state") or "QUERY_STATE_UNKNOWN")
        return DuneExecution(
            execution_id=execution_id,
            state=state,
            is_finished=bool(data.get("is_execution_finished")) or state in _FINISHED_STATES,
            is_failed=state in _FAILED_STATES,
        )

    async def results(self, client: httpx.AsyncClient, execution_id: str) -> list[dict] | None:
        """The result rows, or ``None`` when the payload has no ``result.rows``.

        ``None`` (a data gap) rather than ``[]`` (which aggregates to a happy,
        empty chart) - a truncated or reshaped payload is not "no activity"."""
        data = await self._request(client, "GET", f"/execution/{execution_id}/results")
        if not isinstance(data, dict):
            return None
        rows = (data.get("result") or {}).get("rows")
        if not isinstance(rows, list):
            logger.info("Dune execution %s returned no result.rows", execution_id)
            return None
        return [row for row in rows if isinstance(row, dict)]

    def decode_rows(self, rows: list[dict]) -> list[DuneActivityRow]:
        """Validate rows against the contract, dropping (and logging) bad ones."""
        if rows:
            present = set(rows[0])
            missing = [c for c in _EXPECTED_COLUMNS if c not in present]
            if missing:
                logger.warning(
                    "Dune activity query is missing expected column(s) %s - "
                    "metrics will read as data gaps until the saved query matches "
                    "data/dune/onchain_activity.sql",
                    ", ".join(missing),
                )
        out: list[DuneActivityRow] = []
        for row in rows:
            try:
                out.append(DuneActivityRow.model_validate(row))
            except ValidationError as exc:
                logger.info("Skipping undecodable Dune row (%s): %s", row.get("day"), exc)
        return out

    async def run_activity_query(
        self,
        client: httpx.AsyncClient,
        chain: str,
        addresses: list[str],
        days: int,
    ) -> tuple[list[DuneActivityRow], str] | None:
        """Execute -> poll -> fetch, under one wall-clock deadline.

        Returns ``(rows, execution_id)`` on success and ``None`` when the
        deadline expires. ``None`` is deliberately not an exception: a still
        running execution is not a failure, it is a "come back next pass".
        """
        if not self.api_key or self.query_id is None:
            return None
        deadline = time.monotonic() + self.poll_timeout_seconds
        execution_id = await self.execute(
            client, {"chain": chain, "addresses": addresses, "days": days}
        )
        while True:
            status = await self.execution(client, execution_id)
            if status.is_failed:
                raise DuneError(
                    f"Dune execution {execution_id} ended in {status.state} for {chain}"
                )
            if status.is_finished:
                break
            if time.monotonic() >= deadline:
                logger.info(
                    "Dune execution %s for %s still %s after %.0fs; deferring to the next pass",
                    execution_id,
                    chain,
                    status.state,
                    self.poll_timeout_seconds,
                )
                return None
            await asyncio.sleep(self.poll_interval_seconds)
        rows = await self.results(client, execution_id)
        if rows is None:
            return None
        return self.decode_rows(rows), execution_id
