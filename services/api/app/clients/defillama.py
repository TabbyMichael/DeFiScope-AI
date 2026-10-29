"""Async client for the public DefiLlama API.

Endpoints used (no API key required):
- GET /protocols          - directory of protocols with headline metrics
- GET /protocol/{slug}    - per-protocol detail incl. historical TVL series
- GET /tvl/{slug}         - current TVL scalar
- GET fees.llama.fi /summary/fees/{slug}?dataType=dailyFees|dailyRevenue - fees/revenue
- GET /overview/dexs/{slug}                                              - DEX volume
- GET coins.llama.fi /chart/{coins}?period=1d&span=N                     - peg-price history

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


@dataclass
class FeeRevenueSummary:
    """Fees & revenue pulled from fees.llama.fi. Any field left ``None`` means
    the host had no tracked series for it - surfaced as a data gap, never zero."""

    slug: str
    fees_24h: float | None = None
    fees_7d: float | None = None
    fees_30d: float | None = None
    revenue_24h: float | None = None
    revenue_30d: float | None = None


@dataclass
class DexVolumeSummary:
    """DEX trading volume from the /overview/dexs endpoint. ``None`` when the
    protocol is not a tracked venue (most non-DEX protocols) - a gap, not zero."""

    slug: str
    volume_24h: float | None = None
    volume_7d: float | None = None
    volume_30d: float | None = None


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


def _num(data: Any, key: str) -> float | None:
    """Read a numeric field from a parsed JSON body, tolerating nulls, bools and
    non-dict bodies. Returns ``None`` (a gap) rather than coercing to 0."""
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class DefiLlamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        fees_base_url: str | None = None,
        coins_base_url: str | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.defillama_base_url).rstrip("/")
        self.fees_base_url = (fees_base_url or settings.fees_base_url).rstrip("/")
        self.coins_base_url = (coins_base_url or settings.coins_base_url).rstrip("/")
        self.timeout = timeout or settings.http_timeout_seconds
        self.max_retries = settings.defillama_max_retries if max_retries is None else max_retries

    async def _get(self, client: httpx.AsyncClient, path: str, base_url: str | None = None) -> Any:
        url = f"{(base_url or self.base_url).rstrip('/')}{path}"
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

    async def _get_optional(
        self, client: httpx.AsyncClient, path: str, base_url: str | None = None
    ) -> Any:
        """Best-effort fetch for enrichment endpoints: any upstream or parsing
        failure returns ``None`` so a missing/renamed secondary feed degrades to
        a data gap rather than failing the protocol's whole research pack."""
        try:
            return await self._get(client, path, base_url=base_url)
        except Exception as exc:  # noqa: BLE001 - enrichment is strictly optional
            logger.info("Optional DefiLlama fetch failed for %s: %s", path, exc)
            return None

    async def get_fee_revenue(
        self, client: httpx.AsyncClient, slug: str
    ) -> FeeRevenueSummary | None:
        """Trailing fees & revenue from fees.llama.fi. Two independent dataType
        calls (dailyFees, dailyRevenue); returns ``None`` only when both fail,
        otherwise each field is populated where the host tracked it."""
        fees = await self._get_optional(
            client, f"/summary/fees/{slug}?dataType=dailyFees", base_url=self.fees_base_url
        )
        revenue = await self._get_optional(
            client, f"/summary/fees/{slug}?dataType=dailyRevenue", base_url=self.fees_base_url
        )
        if fees is None and revenue is None:
            return None
        return FeeRevenueSummary(
            slug=slug,
            fees_24h=_num(fees, "total24h"),
            fees_7d=_num(fees, "total7d"),
            fees_30d=_num(fees, "total30d"),
            revenue_24h=_num(revenue, "total24h"),
            revenue_30d=_num(revenue, "total30d"),
        )

    async def get_dex_volume(self, client: httpx.AsyncClient, slug: str) -> DexVolumeSummary | None:
        """DEX trading volume from the /overview/dexs endpoint. ``None`` for
        protocols that are not tracked venues (the common case) - a gap, not 0."""
        data = await self._get_optional(
            client,
            f"/overview/dexs/{slug}?dataType=dailyVolume"
            "&excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true",
        )
        if not isinstance(data, dict):
            return None
        return DexVolumeSummary(
            slug=slug,
            volume_24h=_num(data, "total24h"),
            volume_7d=_num(data, "total7d"),
            volume_30d=_num(data, "total30d"),
        )

    async def get_stablecoin_prices(
        self,
        client: httpx.AsyncClient,
        coin_ids: list[str],
        window_days: int = 30,
    ) -> dict[str, list[tuple[int, float]]]:
        """Peg-price history for a batch of coins via coins.llama.fi ``/chart``.

        Returns ``{coin_id: [(unix_ts, usd_price), ...]}`` (daily points over the
        window). An empty dict on any failure or when nothing parses - i.e. a
        data gap, never a fabricated flat peg. One request fetches every coin the
        protocol mints, so a multi-stablecoin issuer costs a single call."""
        if not coin_ids:
            return {}
        coins = ",".join(coin_ids)
        path = f"/chart/{coins}?period=1d&span={max(1, window_days)}&searchWidth=4h"
        data = await self._get_optional(client, path, base_url=self.coins_base_url)
        if not isinstance(data, dict):
            return {}
        out: dict[str, list[tuple[int, float]]] = {}
        for coin, entry in (data.get("coins") or {}).items():
            if not isinstance(entry, dict):
                continue
            series: list[tuple[int, float]] = []
            for point in entry.get("prices") or []:
                if not isinstance(point, dict):
                    continue
                ts = point.get("timestamp")
                price = point.get("price")
                if ts is None or isinstance(price, bool) or not isinstance(price, (int, float)):
                    continue
                try:
                    series.append((int(ts), float(price)))
                except (TypeError, ValueError):
                    continue
            if series:
                out[coin] = sorted(series)
        return out
