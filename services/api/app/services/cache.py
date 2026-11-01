"""Optional Redis cache for the protocol catalog read surface (Stage 3 perf).

Why this exists
---------------
The discovery catalog list (``GET /api/protocols``) and its facets are the only
hot read paths with no cache today: every page click re-runs two ``COUNT``s plus
a paged ``ORDER BY ... OFFSET`` scan, and the Next route forwards them
``no-store`` on every keystroke. The research-detail path already keeps a 300s
in-process LRU (see ``services/protocols.py``); this covers the list/facet
surface that LRU does not, and survives an API restart.

Honesty + degradation (the app's core contract)
-----------------------------------------------
Redis is *strictly optional*. When ``redis_url`` is unset (the default), or the
server is down, every helper here is a no-op that reports a miss, so reads fall
through to the exact database path they use today - never an error, never a
fabricated value. Nothing user-facing regresses if Redis disappears: the cache
is a pure speedup, never a source of truth (Postgres still is).

Correctness rules baked into the key scheme:

- Keys are namespaced and **versioned**. A catalog mutation bumps one version
  counter (``bump_version``), so every current page/facet entry simply becomes
  unreachable and expires - no SCAN-and-delete, and (because the catalog changes
  only via a sync) the invalidation is exact, not best-effort.
- Keys carry a **scope fingerprint**. Catalog pages are ABAC-filtered, so one
  subject's filtered page can never be served from another subject's entry.
- Only **successful** results are ever stored; a raised exception is never
  cached, so a transient DB error cannot stick.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Protocol

from app.config import get_settings
from app.security.principal import Scope

logger = logging.getLogger(__name__)

# Namespace/versioned prefix. Bumping the leading "v1" is a manual full flush.
NS = "defiscope:v1"
_VERSION_KEY = f"{NS}:catalog:version"
_LOCK_PREFIX = f"{NS}:flight:"
# ``0`` means "never bumped since the server started": an absent version key
# reads back as 0. Redis ``INCR`` on a missing key yields 1, so the sentinel
# *must* be 0 - otherwise the very first ``bump_version`` would store 1 over an
# implicit 1 and the initial invalidation would be a silent no-op, letting pages
# cached before the first sync survive it.
_DEFAULT_VERSION = 0


class KVClient(Protocol):
    """The tiny slice of the Redis command surface we use.

    Narrow on purpose: production wraps ``redis.asyncio`` and tests inject an
    in-memory fake, so no test ever needs (or is allowed to reach) a live Redis -
    the same hermetic posture ``conftest`` uses to neutralise Dune and OpenAI."""

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ex: int | None = None) -> object: ...

    async def set_nx(self, key: str, value: str, px: int | None = None) -> bool: ...

    async def delete(self, key: str) -> object: ...

    async def incr(self, key: str) -> int: ...

    async def aclose(self) -> None: ...


class _RedisKV:
    """Adapter over ``redis.asyncio`` so one wrapper covers get/set/incr/nx."""

    def __init__(self, redis: object) -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:  # pragma: no cover - real Redis
        return await self._redis.get(key)  # type: ignore[attr-defined]

    async def set(self, key: str, value: str, ex: int | None = None) -> object:  # pragma: no cover
        return await self._redis.set(key, value, ex=ex)  # type: ignore[attr-defined]

    async def set_nx(self, key: str, value: str, px: int | None = None) -> bool:  # pragma: no cover
        return bool(await self._redis.set(key, value, nx=True, px=px))  # type: ignore[attr-defined]

    async def delete(self, key: str) -> object:  # pragma: no cover - real Redis
        return await self._redis.delete(key)  # type: ignore[attr-defined]

    async def incr(self, key: str) -> int:  # pragma: no cover - real Redis
        return int(await self._redis.incr(key))  # type: ignore[attr-defined]

    async def aclose(self) -> None:  # pragma: no cover - real Redis
        await self._redis.aclose()  # type: ignore[attr-defined]


_UNSET = object()
# Module-level singleton: ``_UNSET`` means "not built yet", ``None`` means
# "caching is off / unavailable", otherwise it is a ready :class:`KVClient`.
_client: KVClient | None | object = _UNSET


def _build_client() -> KVClient | None:
    settings = get_settings()
    if not settings.cache_ready:
        return None
    try:  # pragma: no cover - exercised only against a real Redis
        import redis.asyncio as aioredis

        return _RedisKV(aioredis.from_url(settings.redis_url, decode_responses=True))
    except Exception as exc:  # noqa: BLE001 - the cache must never be fatal
        logger.warning(
            "Redis cache unavailable (%s); catalog reads served from the database",
            type(exc).__name__,
        )
        return None


def get_client() -> KVClient | None:
    """The process-wide cache client, or ``None`` when caching is off/broken."""
    global _client
    if _client is _UNSET:
        _client = _build_client()
    return _client  # type: ignore[return-value]


def set_client(client: KVClient | None) -> None:
    """Inject a client. Tests pass an in-memory fake; production never calls this."""
    global _client
    _client = client


def reset_client() -> None:
    """Drop the memoized client so the next ``get_client`` rebuilds from config."""
    global _client
    _client = _UNSET


# --- key builders -----------------------------------------------------------


def scope_fingerprint(scope: Scope | None) -> str:
    """A stable id for the caller's data scope, so cache entries never cross
    subjects. Unrestricted scopes (auth ``off``, or an admin) collapse to one
    shared ``public`` bucket, which is exactly the population that may see all."""
    if scope is None or not scope.restricted:
        return "public"
    cats = ",".join(sorted(scope.categories)) if scope.categories is not None else ""
    chains = ",".join(sorted(scope.chains)) if scope.chains is not None else ""
    digest = hashlib.sha1(f"{cats}\x1f{chains}".encode()).hexdigest()
    return digest[:16]


def catalog_page_key(
    version: int,
    *,
    q: str | None,
    chain: str | None,
    category: str | None,
    band: str | None,
    sort: str,
    order: str,
    page: int,
    page_size: int,
    scope: Scope | None,
) -> str:
    """Key one catalog page by every parameter that can change its rows.

    ``q`` is lowercased because the backend search is a case-insensitive
    ``ILIKE``: "AAVE" and "aave" answer identically and should share an entry,
    never fork into two. ``chain``/``category``/``band`` are exact-match filters,
    so their case is preserved."""
    filters = "\x1f".join(
        (
            (q or "").strip().lower(),
            (chain or "").strip(),
            (category or "").strip(),
            (band or "").strip(),
            sort,
            order,
            str(page),
            str(page_size),
        )
    )
    fh = hashlib.sha1(filters.encode()).hexdigest()[:20]
    return f"{NS}:catalog:{version}:{fh}:{scope_fingerprint(scope)}"


def facets_key(version: int) -> str:
    """Facets are global today (``catalog_facets`` ignores scope), so they are
    keyed by version only - deliberate parity with the current unscoped read."""
    return f"{NS}:facets:{version}"


# --- read / write helpers (each degrades to a miss on any fault) ------------


async def get_json(key: str) -> dict | None:
    """Return a cached object, or ``None`` on a miss or *any* cache fault."""
    client = get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 - a cache fault must never fail a read
        logger.warning(
            "Catalog cache read failed (%s); serving from database", type(exc).__name__
        )
        return None


async def set_json(key: str, payload: dict, ttl_seconds: int) -> None:
    """Store a *successful* result. Faults are swallowed: a failed write only
    costs the next reader a recompute, never correctness."""
    client = get_client()
    if client is None:
        return
    try:
        await client.set(key, json.dumps(payload), ex=max(1, int(ttl_seconds)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Catalog cache write failed (%s); ignoring", type(exc).__name__)


async def get_version() -> int:
    """Current catalog namespace version (one cheap GET per request)."""
    client = get_client()
    if client is None:
        return _DEFAULT_VERSION
    try:
        raw = await client.get(_VERSION_KEY)
        return int(raw) if raw else _DEFAULT_VERSION
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Catalog cache version read failed (%s); assuming baseline", type(exc).__name__
        )
        return _DEFAULT_VERSION


async def bump_version() -> None:
    """Advance the catalog version so every current page/facet entry becomes
    unreachable and expires. Called right after any catalog mutation."""
    client = get_client()
    if client is None:
        return
    try:
        await client.incr(_VERSION_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Catalog cache version bump failed (%s); TTL still bounds staleness",
            type(exc).__name__,
        )


async def try_lock(key: str, ttl_ms: int = 5000) -> bool:
    """Best-effort single-flight guard. Returns ``True`` when this caller may go
    populate ``key`` (it took the short lock) - and also when caching is off or
    the lock command faults, so the miss path always makes progress. ``False``
    means a sibling is already filling it and should wait briefly."""
    client = get_client()
    if client is None:
        return True
    try:
        return await client.set_nx(_LOCK_PREFIX + key, "1", px=ttl_ms)
    except Exception:  # noqa: BLE001 - on any fault, just proceed and compute
        return True


async def release_lock(key: str) -> None:
    """Drop a held flight lock so the next miss can take it (best-effort)."""
    client = get_client()
    if client is None:
        return
    try:
        await client.delete(_LOCK_PREFIX + key)
    except Exception:  # noqa: BLE001 - the lock self-expires via PX regardless
        pass


async def aclose() -> None:
    """Close the underlying client on shutdown. Never *builds* one just to close
    it, and always clears the singleton so a restart re-reads config."""
    global _client
    client = _client if _client is not _UNSET else None
    try:
        if client is not None:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001 - shutdown must not raise
        logger.warning("Catalog cache close failed (%s)", type(exc).__name__)
    finally:
        reset_client()
