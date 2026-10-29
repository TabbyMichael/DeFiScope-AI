"""Async client for the public DefiLlama API.

Endpoints used (no API key required):
- GET /protocols          - directory of protocols with headline metrics
- GET /protocol/{slug}    - per-protocol detail incl. historical TVL series
- GET /tvl/{slug}         - current TVL scalar

Documentation: https://defillama.com/docs/api
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Transient upstream statuses worth another attempt (rate limit / server blip).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _retry_delay_seconds(response: httpx.Response | None, attempt: int) -> float:
    """Seconds to wait before the next attempt.

    Honors a numeric ``Retry-After`` header when present (DefiLlama/CDN rate
    limits), otherwise falls back to capped exponential backoff with jitter so
    concurrent crawls don't retry in lockstep."""
    if response is not None:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return max(0.0, float(raw))
            except ValueError:
                pass
    base = min(8.0, (2**attempt) * 0.5)
    return base + random.uniform(0, 0.25)


class DefiLlamaError(RuntimeError):
    """Raised when the DefiLlama API is unreachable or returns unexpected data."""


@dataclass
class ProtocolSummary:
    """Normalized subset of the /protocols listing entry."""

    slug: str
    name: str
    category: str | None = None
    symbol: str | None = None
    chains: list[str] = field(default_factory=list)
    tvl: float | None = None
    change_1d: float | None = None
    change_7d: float | None = None
    change_1m: float | None = None
    audits: str | None = None
    url: str | None = None
    listing_timestamp: int | None = None


@dataclass
class ProtocolDetail:
    """Normalized subset of the /protocol/{slug} response."""

    slug: str
    name: str
    current_chain_tvls: dict[str, float]
    tvl_history: list[tuple[int, float]]  # (unix timestamp, USD value)
    staking_history: list[tuple[int, float]]
    borrowed_history: list[tuple[int, float]]
    extra: dict[str, Any] = field(default_factory=dict)


def _extract_series(raw: Any) -> list[tuple[int, float]]:
    """DefiLlama returns TVL history either as a list of {date, totalLiquidityUSD}
    dicts, or (for some protocols) as a dict keyed by chain. Handles both."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        # dict of chain -> series
        merged: dict[int, float] = {}
        for series in raw.values():
            for point in _extract_series(series):
                merged[point[0]] = merged.get(point[0], 0.0) + point[1]
        return sorted(merged.items())
    if isinstance(raw, list):
        out: list[tuple[int, float]] = []
        for point in raw:
            if not isinstance(point, dict):
                continue
            date = point.get("date")
            value = point.get("totalLiquidityUSD", point.get("tvl"))
            if date is None or value is None:
                continue
            try:
                out.append((int(date), float(value)))
            except (TypeError, ValueError):
                continue
        return sorted(out)
    return []


class DefiLlamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.defillama_base_url).rstrip("/")
        self.timeout = timeout or settings.http_timeout_seconds
        self.max_retries = settings.defillama_max_retries if max_retries is None else max_retries

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        url = f"{self.base_url}{path}"
        attempts = max(1, self.max_retries + 1)
        for attempt in range(attempts):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # 404 = missing protocol: never retry, surface as a not-found.
                if status == 404:
                    raise DefiLlamaError(f"Protocol not found: {path}") from exc
                # Retry transient upstream failures with backoff; else give up.
                if status in _RETRYABLE_STATUS and attempt < attempts - 1:
                    delay = _retry_delay_seconds(exc.response, attempt)
                    logger.warning(
                        "DefiLlama %s for %s; retrying in %.2fs (attempt %d/%d)",
                        status,
                        url,
                        delay,
                        attempt + 1,
                        attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise DefiLlamaError(f"DefiLlama error {status} for {url}") from exc
            except httpx.TransportError as exc:
                if attempt < attempts - 1:
                    delay = _retry_delay_seconds(None, attempt)
                    logger.warning(
                        "DefiLlama transport error for %s (%s); retrying in %.2fs (attempt %d/%d)",
                        url,
                        exc,
                        delay,
                        attempt + 1,
                        attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise DefiLlamaError(f"DefiLlama request failed for {url}: {exc}") from exc
            except ValueError as exc:
                # Malformed/non-JSON body is not a transient failure - retrying
                # the same response would just fail again.
                raise DefiLlamaError(f"DefiLlama request failed for {url}: {exc}") from exc
        # Unreachable: every loop branch returns or raises. Kept for type-safety.
        raise DefiLlamaError(f"DefiLlama request failed for {url} after {attempts} attempts")

    async def list_protocols(self, client: httpx.AsyncClient) -> list[ProtocolSummary]:
        raw = await self._get(client, "/protocols")
        if not isinstance(raw, list):
            raise DefiLlamaError("Unexpected /protocols response shape")
        out = []
        for entry in raw:
            try:
                out.append(
                    ProtocolSummary(
                        slug=entry["slug"],
                        name=entry.get("name") or entry["slug"],
                        category=entry.get("category"),
                        symbol=entry.get("symbol"),
                        chains=entry.get("chains") or [],
                        tvl=float(entry["tvl"]) if entry.get("tvl") is not None else None,
                        change_1d=entry.get("change_1d"),
                        change_7d=entry.get("change_7d"),
                        change_1m=entry.get("change_1m"),
                        audits=str(entry["audits"]) if entry.get("audits") is not None else None,
                        url=entry.get("url"),
                        listing_timestamp=entry.get("listingTimestamp"),
                    )
                )
            except (KeyError, TypeError, ValueError):
                logger.warning("Skipping malformed /protocols entry: %s", entry.get("slug"))
        return out

    async def get_protocol(self, client: httpx.AsyncClient, slug: str) -> ProtocolDetail:
        raw = await self._get(client, f"/protocol/{slug}")
        if not isinstance(raw, dict):
            raise DefiLlamaError(f"Unexpected /protocol/{slug} response shape")
        chain_tvls = {
            str(chain): float(value)
            for chain, value in (raw.get("currentChainTvls") or {}).items()
            if isinstance(value, (int, float))
        }
        return ProtocolDetail(
            slug=raw.get("slug") or slug,
            name=raw.get("name") or slug,
            current_chain_tvls=chain_tvls,
            tvl_history=_extract_series(raw.get("tvl")),
            staking_history=_extract_series(raw.get("staking") or raw.get("stakingTvls")),
            borrowed_history=_extract_series(raw.get("borrowed")),
            extra={
                "parentProtocol": raw.get("parentProtocol"),
                "description": raw.get("description"),
            },
        )
