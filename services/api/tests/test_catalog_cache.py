"""Redis catalog cache (performance roadmap Stage 3).

Covers the four properties that matter for a cache bolted onto the app's honesty
contract: it *works* (hit/miss/invalidation), it can never leak one subject's
page to another (scope-safe keys), it never stores a failure (errors are not
cached), and - above all - it is *strictly optional*: with no Redis (or a broken
one) every catalog read degrades to the exact database path it used before, so
the cache is a speedup and never a dependency or a source of truth.

No test here reaches a live Redis. ``conftest`` pins ``DEFISCOPE_REDIS_URL``
empty so the real client is never built; the cache logic is exercised through an
injected in-memory fake - the same posture used to neutralise Dune and OpenAI.
"""

from __future__ import annotations

import types

import httpx
import pytest
from app.clients.defillama import ProtocolSummary
from app.config import get_settings
from app.db import Base, ProtocolCatalog, ProtocolCatalogChain, SessionLocal, engine
from app.main import app
from app.security.principal import Scope
from app.services import cache, catalog
from app.services.protocols import ProtocolResearchService


def _summaries(n: int) -> list[ProtocolSummary]:
    return [
        ProtocolSummary(
            slug=f"proto-{i:05d}",
            name=f"Proto {i:05d}",
            category="Lending",
            chains=["Ethereum"],
            tvl=float(i * 1000),
        )
        for i in range(n)
    ]


class FakeKV:
    """A minimal in-memory stand-in for ``redis.asyncio`` (the KVClient protocol).

    Records get/set traffic so a test can prove *whether* the database was
    consulted, not just what came back."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.gets = 0
        self.sets = 0

    async def get(self, key: str) -> str | None:
        self.gets += 1
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> object:
        self.sets += 1
        self.store[key] = value
        return True

    async def set_nx(self, key: str, value: str, px: int | None = None) -> bool:
        if key in self.store:
            return False
        self.store[key] = value
        return True

    async def delete(self, key: str) -> object:
        self.store.pop(key, None)
        return 1

    async def incr(self, key: str) -> int:
        n = int(self.store.get(key, 0)) + 1
        self.store[key] = str(n)
        return n

    async def aclose(self) -> None:
        pass


class FaultyKV:
    """Every command raises - a Redis that is down mid-request."""

    async def get(self, key: str) -> str:
        raise RuntimeError("redis down")

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        raise RuntimeError("redis down")

    async def set_nx(self, key: str, value: str, px: int | None = None) -> bool:
        raise RuntimeError("redis down")

    async def delete(self, key: str) -> bool:
        raise RuntimeError("redis down")

    async def incr(self, key: str) -> int:
        raise RuntimeError("redis down")

    async def aclose(self) -> None:
        raise RuntimeError("redis down")


@pytest.fixture(autouse=True)
def _isolate_cache():
    """Never let an injected client leak across tests: force a rebuild (which,
    with the empty test URL, resolves to ``None`` = caching disabled)."""
    cache.reset_client()
    yield
    cache.reset_client()


@pytest.fixture(autouse=True)
def _clean_catalog():
    Base.metadata.create_all(engine)
    sess = SessionLocal()
    try:
        sess.query(ProtocolCatalogChain).delete()
        sess.query(ProtocolCatalog).delete()
        sess.commit()
    finally:
        sess.close()


@pytest.fixture()
def fake():
    client = FakeKV()
    cache.set_client(client)
    return client


@pytest.fixture()
def faulty():
    client = FaultyKV()
    cache.set_client(client)
    return client


@pytest.fixture()
def session():
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture()
async def client():
    # Cold-start sync off: these tests seed directly, so a read never touches the
    # network (a warm catalog short-circuits ``ensure_populated``).
    settings = get_settings()
    previous = settings.catalog_sync_on_startup
    settings.catalog_sync_on_startup = False
    app.state.http = httpx.AsyncClient()
    app.state.research_service = ProtocolResearchService()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    await app.state.http.aclose()
    settings.catalog_sync_on_startup = previous


def _spy_query(monkeypatch) -> dict[str, int]:
    """Count how often the *real* DB query runs (a cache hit must not call it)."""
    calls = {"n": 0}
    real = catalog.query_catalog

    def wrapper(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(catalog, "query_catalog", wrapper)
    return calls


# --- the honest default: no Redis => every read is the plain DB path ----------


async def test_disabled_cache_always_hits_the_db(client, session, monkeypatch):
    # ``_isolate_cache`` leaves the client unbuilt and the test URL is empty, so
    # ``cache_ready`` is False and every helper no-ops - the pre-cache behaviour.
    assert get_settings().cache_ready is False
    catalog.sync_catalog(session, _summaries(5))
    calls = _spy_query(monkeypatch)
    first = await client.get("/api/protocols?page_size=25")
    second = await client.get("/api/protocols?page_size=25")
    assert first.status_code == 200 and second.status_code == 200
    # No cache => both requests compute; nothing is ever stored.
    assert calls["n"] == 2
    assert first.json() == second.json()


# --- hit / miss / invalidation (the cache actually working) -------------------


async def test_second_identical_read_is_served_from_cache(client, session, fake, monkeypatch):
    catalog.sync_catalog(session, _summaries(30))
    calls = _spy_query(monkeypatch)

    first = await client.get("/api/protocols?page_size=25&page=1")
    assert first.status_code == 200
    assert calls["n"] == 1  # cold: computed from the DB
    assert fake.sets >= 1  # and then stored

    second = await client.get("/api/protocols?page_size=25&page=1")
    assert calls["n"] == 1  # warm: the DB was NOT consulted again
    assert second.json() == first.json()  # byte-for-byte the same page


async def test_different_page_is_a_different_key(client, session, fake, monkeypatch):
    catalog.sync_catalog(session, _summaries(30))
    calls = _spy_query(monkeypatch)
    await client.get("/api/protocols?page_size=25&page=1")
    await client.get("/api/protocols?page_size=25&page=2")
    # A distinct page must not be answered from page 1's entry.
    assert calls["n"] == 2


async def test_bump_version_retires_cached_pages(client, session, fake, monkeypatch):
    catalog.sync_catalog(session, _summaries(30))
    calls = _spy_query(monkeypatch)
    await client.get("/api/protocols?page_size=25&page=1")
    assert calls["n"] == 1
    await client.get("/api/protocols?page_size=25&page=1")
    assert calls["n"] == 1  # served from cache

    await cache.bump_version()  # what a catalog sync does on completion

    await client.get("/api/protocols?page_size=25&page=1")
    assert calls["n"] == 2  # version moved => the old entry is unreachable


async def test_sync_from_source_bumps_the_version(session, fake):
    # The mutation entry point must invalidate, or a sync would leave stale pages.
    before = await cache.get_version()

    class StubLlama:
        async def list_protocols(self, http):
            return _summaries(2)

    # No network: the pure upsert is stubbed; we only assert the bump fires.
    def _fake_sync(sess, summaries, now=None):
        return types.SimpleNamespace(inserted=len(summaries))

    original = catalog.sync_catalog
    catalog.sync_catalog = _fake_sync
    try:
        await catalog.sync_from_source(session, StubLlama(), None)
    finally:
        catalog.sync_catalog = original

    after = await cache.get_version()
    assert after == before + 1


# --- scope-safe keys: one subject's page can never be replayed to another -----


def test_keys_isolate_by_scope():
    def key(scope):
        return cache.catalog_page_key(
            1, q=None, chain=None, category=None, band=None,
            sort="tvl", order="desc", page=1, page_size=25, scope=scope,
        )

    unrestricted = Scope()
    lending = Scope(categories=frozenset({"Lending"}))
    dexes = Scope(categories=frozenset({"Dexes"}))

    assert cache.scope_fingerprint(unrestricted) == "public"
    # Two restricted subjects never share an entry...
    assert key(lending) != key(dexes)
    # ...and an unrestricted caller does not collide with either.
    assert key(unrestricted) != key(lending)
    # Same scope => same key (so a warm entry is actually reused).
    assert key(lending) == key(Scope(categories=frozenset({"Lending"})))


def test_public_scope_fingerprint_is_stable():
    assert cache.scope_fingerprint(None) == "public"
    assert cache.scope_fingerprint(Scope(chains=frozenset({"Ethereum"}))) == (
        cache.scope_fingerprint(Scope(chains=frozenset({"Ethereum"})))
    )


# --- the cache must never stick a failure or fake a value ---------------------


async def test_query_error_is_never_cached(client, session, fake, monkeypatch):
    catalog.sync_catalog(session, _summaries(5))

    def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(catalog, "query_catalog", _boom)
    with pytest.raises(RuntimeError):
        await client.get("/api/protocols?page_size=25")
    # The exception fired before any set_json, so nothing erroneous was stored.
    assert fake.sets == 0


async def test_down_redis_degrades_to_the_database(client, session, faulty, monkeypatch):
    catalog.sync_catalog(session, _summaries(30))
    calls = _spy_query(monkeypatch)
    # Every Redis command raises, yet the read must succeed exactly as uncached.
    resp = await client.get("/api/protocols?page_size=25&page=1")
    assert resp.status_code == 200
    assert resp.json()["total"] == 30
    assert calls["n"] == 1  # served by the DB, not a cache fault surfaced as a 500
