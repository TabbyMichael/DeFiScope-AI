"""Protocol discovery catalog: ingestion (idempotent upsert) + paginated reads.

These cover the 5,000+ catalog feature end to end at the service layer (sync,
dedup, upsert, non-destructive re-sync, search, filter, sort, null ordering,
scope narrowing) and the HTTP layer (pagination metadata, page-size / param
validation, empty results). The 5,000-record synthetic sync also records wall
clock timings so a performance regression fails the suite rather than drifting.
"""

from __future__ import annotations

import time

import httpx
import pytest
from app.db import Base, ProtocolCatalog, ProtocolCatalogChain, SessionLocal, engine
from app.main import app
from app.security.principal import Scope
from app.services import catalog
from app.services.protocols import ProtocolResearchService

CATEGORIES = ["Lending", "Dexes", "Liquid Staking", "Bridges", "Yield"]
CHAINS = ["Ethereum", "Arbitrum", "Base", "Solana", "Optimism"]


def make_summary(i: int, **overrides):
    base = {
        "slug": f"proto-{i:05d}",
        "name": f"Proto {i:05d}",
        "category": CATEGORIES[i % len(CATEGORIES)],
        "symbol": f"P{i}",
        "chains": [CHAINS[i % len(CHAINS)], CHAINS[(i + 1) % len(CHAINS)]],
        "tvl": float(i * 1000),
        "change_1d": 1.0,
        "change_7d": 2.0,
        "change_1m": 3.0,
        "audits": "2",
        "url": f"https://proto{i}.example",
        "listing_timestamp": 1_600_000_000 + i,
    }
    base.update(overrides)
    from app.clients.defillama import ProtocolSummary

    return ProtocolSummary(**base)


def summaries(n: int) -> list:
    return [make_summary(i) for i in range(n)]


@pytest.fixture(autouse=True)
def _clean_catalog():
    """A predictable catalog table for every test (shared SQLite ``test.db``)."""
    Base.metadata.create_all(engine)
    sess = SessionLocal()
    try:
        sess.query(ProtocolCatalogChain).delete()
        sess.query(ProtocolCatalog).delete()
        sess.commit()
    finally:
        sess.close()
    yield


@pytest.fixture()
def session():
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture()
async def client():
    # Disable the cold-start directory sync: these endpoint tests seed the
    # catalog directly through the service, so no test ever reaches the network.
    from app.config import get_settings

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


class TestSyncIngestion:
    def test_inserts_and_reports_counts(self, session):
        stats = catalog.sync_catalog(session, summaries(3))
        assert stats.fetched == 3
        assert stats.inserted == 3
        assert stats.updated == 0
        assert stats.total_after == 3
        # Chain membership is normalized into the join table.
        chains = session.query(ProtocolCatalogChain).count()
        assert chains == 6  # 2 distinct chains per protocol

    def test_idempotent_re_sync(self, session):
        catalog.sync_catalog(session, summaries(3))
        second = catalog.sync_catalog(session, summaries(3))
        assert second.inserted == 0
        assert second.updated == 0  # identical metadata -> unchanged
        assert second.unchanged == 3
        assert catalog.catalog_count(session) == 3

    def test_updates_only_changed_metadata(self, session):
        catalog.sync_catalog(session, summaries(3))
        changed = [make_summary(0, tvl=999_000.0), make_summary(1), make_summary(2)]
        stats = catalog.sync_catalog(session, changed)
        assert stats.updated == 1
        assert stats.unchanged == 2
        row = session.get(ProtocolCatalog, "proto-00000")
        assert row.tvl == 999_000.0

    def test_never_deletes_protocols_absent_from_provider(self, session):
        catalog.sync_catalog(session, summaries(3))  # proto-00000..2
        # A later listing that dropped proto-00002 must not erase it.
        catalog.sync_catalog(session, [make_summary(0), make_summary(1)])
        assert catalog.catalog_count(session) == 3
        assert session.get(ProtocolCatalog, "proto-00002") is not None

    def test_duplicate_slugs_are_deduplicated(self, session):
        dup = [make_summary(0), make_summary(0), make_summary(1)]
        stats = catalog.sync_catalog(session, dup)
        assert stats.duplicates == 1
        assert stats.inserted == 2
        assert catalog.catalog_count(session) == 2

    def test_malformed_entries_are_skipped_not_fatal(self, session):
        from app.clients.defillama import ProtocolSummary

        bad = ProtocolSummary(slug="", name="No Slug")  # unusable: no identity
        stats = catalog.sync_catalog(session, [bad, make_summary(0)])
        assert stats.skipped == 1
        assert stats.inserted == 1

    def test_metadata_resync_preserves_analysis_fields(self, session):
        catalog.sync_catalog(session, summaries(1))
        # A monitoring pass scores the protocol after it was discovered.
        catalog.refresh_analysis(session, [("proto-00000", 42.0, "moderate")])
        # A re-sync must not clobber the score - discovery owns metadata only.
        catalog.sync_catalog(session, [make_summary(0, tvl=123.0)])
        row = session.get(ProtocolCatalog, "proto-00000")
        assert row.tvl == 123.0  # metadata refreshed
        assert row.risk_score == 42.0  # analysis preserved
        assert row.risk_band == "moderate"
        assert row.monitored == 1

    def test_normalization_trims_and_dedups_chains(self, session):
        from app.clients.defillama import ProtocolSummary

        s = ProtocolSummary(
            slug="  spaced-slug  ",
            name="  Spaced Name  ",
            category=" Lending ",
            chains=["Ethereum", "ethereum", "Ethereum", "", "Base"],
            tvl=5.0,
        )
        catalog.sync_catalog(session, [s])
        row = session.get(ProtocolCatalog, "spaced-slug")
        assert row is not None
        assert row.name == "Spaced Name"
        assert row.category == "Lending"
        # Exact-duplicate chains collapse; case differs so "ethereum" stays a
        # distinct entry from "Ethereum" (we never silently merge provider data).
        assert row.chains == sorted(["Ethereum", "ethereum", "Base"])


class TestQueryPagination:
    def test_page_metadata_and_boundaries(self, session):
        catalog.sync_catalog(session, summaries(5))
        items, total, pages = catalog.query_catalog(session, page=1, page_size=2)
        assert total == 5
        assert pages == 3
        assert len(items) == 2
        # Last page returns the partial remainder, not an empty page.
        last, _, _ = catalog.query_catalog(session, page=3, page_size=2)
        assert len(last) == 1
        # Beyond the end is empty but keeps the correct total.
        beyond, total_after, _ = catalog.query_catalog(session, page=9, page_size=2)
        assert beyond == []
        assert total_after == 5

    def test_empty_catalog_returns_empty_page(self, session):
        items, total, pages = catalog.query_catalog(session, page=1, page_size=25)
        assert items == []
        assert total == 0
        assert pages == 0

    def test_search_by_name_and_slug(self, session):
        catalog.sync_catalog(session, summaries(10))
        by_name, total, _ = catalog.query_catalog(session, q="Proto 00007")
        assert total == 1
        assert by_name[0].slug == "proto-00007"
        by_slug, total2, _ = catalog.query_catalog(session, q="proto-00003")
        assert total2 >= 1
        assert any(i.slug == "proto-00003" for i in by_slug)

    def test_search_escapes_like_wildcards(self, session):
        catalog.sync_catalog(session, summaries(3))
        # A literal '%' must not match everything.
        _, total, _ = catalog.query_catalog(session, q="%")
        assert total == 0

    def test_filter_by_category_and_chain(self, session):
        catalog.sync_catalog(session, summaries(20))
        _, cat_total, _ = catalog.query_catalog(session, category="Lending")
        items, _, _ = catalog.query_catalog(session, category="Lending", page_size=100)
        assert all(i.category == "Lending" for i in items)
        assert cat_total == len(items)
        eth, chain_total, _ = catalog.query_catalog(session, chain="Ethereum", page_size=100)
        assert chain_total > 0
        assert all("Ethereum" in i.chains for i in eth)

    def test_sort_by_tvl_desc_then_asc_is_deterministic(self, session):
        catalog.sync_catalog(session, summaries(5))
        desc, _, _ = catalog.query_catalog(session, sort="tvl", order="desc", page_size=100)
        asc, _, _ = catalog.query_catalog(session, sort="tvl", order="asc", page_size=100)
        tvls = [i.tvl for i in desc]
        assert tvls == sorted(tvls, reverse=True)
        assert [i.slug for i in asc] == [i.slug for i in reversed(desc)]

    def test_null_tvl_sinks_last_regardless_of_direction(self, session):
        from app.clients.defillama import ProtocolSummary

        rows = [
            make_summary(0),
            ProtocolSummary(slug="null-tvl", name="Null TVL", tvl=None),
            make_summary(1),
        ]
        catalog.sync_catalog(session, rows)
        desc, _, _ = catalog.query_catalog(session, sort="tvl", order="desc", page_size=100)
        asc, _, _ = catalog.query_catalog(session, sort="tvl", order="asc", page_size=100)
        assert desc[-1].slug == "null-tvl"
        assert asc[-1].slug == "null-tvl"

    def test_sort_by_name_and_updated(self, session):
        catalog.sync_catalog(session, summaries(4))
        names, _, _ = catalog.query_catalog(session, sort="name", order="asc", page_size=100)
        assert [i.name for i in names] == sorted(i.name for i in names)
        upd, _, _ = catalog.query_catalog(session, sort="updated", order="desc", page_size=100)
        stamps = [i.updated_at for i in upd]
        assert stamps == sorted(stamps, reverse=True)

    def test_filter_by_risk_band_includes_null_as_unknown(self, session):
        catalog.sync_catalog(session, summaries(6))
        # Score two rows into distinct bands; the rest keep a NULL band.
        catalog.refresh_analysis(
            session,
            [("proto-00000", 90.0, "high"), ("proto-00001", 20.0, "low")],
        )
        high, high_total, _ = catalog.query_catalog(session, band="high", page_size=100)
        assert high_total == 1 and high[0].slug == "proto-00000"
        # "unknown" must match the NULL-band (never-scored) rows, not just rows
        # explicitly written as the string "unknown".
        _, unknown_total, _ = catalog.query_catalog(session, band="unknown", page_size=100)
        assert unknown_total == 4  # 6 synced - 2 scored

    def test_sort_by_available_risk_score(self, session):
        catalog.sync_catalog(session, summaries(5))
        catalog.refresh_analysis(
            session, [("proto-00002", 80.0, "high"), ("proto-00004", 10.0, "low")]
        )
        items, _, _ = catalog.query_catalog(session, sort="risk", order="desc", page_size=100)
        # Scored rows first (80, 10), then the unscored as a trailing gap block.
        scored = [i.risk_score for i in items if i.risk_score is not None]
        assert scored == [80.0, 10.0]
        assert items[0].risk_score == 80.0
        assert items[-1].risk_score is None

    def test_scope_narrows_results_and_total(self, session):
        catalog.sync_catalog(session, summaries(20))
        lending = Scope(categories=frozenset({"Lending"}))
        items, total, _ = catalog.query_catalog(session, scope=lending, page_size=100)
        assert total == len(items)
        assert all(i.category == "Lending" for i in items)
        assert 0 < total < 20

    def test_scope_denies_unknown_category_when_restricted(self, session):
        from app.clients.defillama import ProtocolSummary

        catalog.sync_catalog(
            session,
            [make_summary(0), ProtocolSummary(slug="no-cat", name="No Category", category=None)],
        )
        restricted = Scope(categories=frozenset({"Lending"}))
        items, total, _ = catalog.query_catalog(session, scope=restricted, page_size=100)
        # The category-less protocol is denied, not silently included.
        assert "no-cat" not in {i.slug for i in items}
        assert total == 1


class TestCatalogEndpoints:
    async def test_paginated_read_is_db_only(self, client, session):
        # Seed directly so no /protocols request is needed; a warm catalog never
        # touches the network on read. page_size must be an allowed contract size.
        catalog.sync_catalog(session, summaries(30))
        resp = await client.get("/api/protocols?page_size=25&page=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 30
        assert body["page_size"] == 25
        assert body["pages"] == 2
        assert len(body["items"]) == 25
        # Second page carries the remainder and never overlaps the first.
        second = (await client.get("/api/protocols?page_size=25&page=2")).json()
        assert len(second["items"]) == 5
        first_slugs = {i["slug"] for i in body["items"]}
        assert first_slugs.isdisjoint(i["slug"] for i in second["items"])

    async def test_empty_catalog_is_200_not_error(self, client, session):
        # Cold-start sync is disabled for this fixture and the table is empty, so
        # the honest answer is an empty page, not a 502 or a crash.
        resp = await client.get("/api/protocols")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    @pytest.mark.parametrize(
        "query",
        [
            "page_size=30",  # not an allowed size
            "page_size=7",
            "page=0",
            "page=-1",
            "sort=gross_revenue",  # not in the allowlist
            "order=sideways",
            "sort=" + "x" * 50,
            "q=" + "z" * 200,  # exceeds max length
        ],
    )
    async def test_invalid_query_params_are_422(self, client, session, query):
        catalog.sync_catalog(session, summaries(1))
        resp = await client.get(f"/api/protocols?{query}")
        assert resp.status_code == 422, query

    async def test_facets_lists_categories_and_chains(self, client, session):
        catalog.sync_catalog(session, summaries(10))
        resp = await client.get("/api/protocols/facets")
        assert resp.status_code == 200
        facets = resp.json()
        assert "Lending" in facets["categories"]
        assert "Ethereum" in facets["chains"]


class TestScaleAndPerformance:
    def test_sync_5000_and_paginate(self, session):
        n = 5000
        data = summaries(n)

        start = time.perf_counter()
        stats = catalog.sync_catalog(session, data)
        sync_seconds = time.perf_counter() - start

        assert stats.inserted == n
        assert catalog.catalog_count(session) == n

        # Warm the first page, then time a couple of representative reads.
        read_start = time.perf_counter()
        first, total, pages = catalog.query_catalog(session, page=1, page_size=100, sort="tvl")
        _ = catalog.query_catalog(session, page=pages, page_size=25, sort="name", order="asc")
        _ = catalog.query_catalog(session, q="Proto 04", page_size=50, category="Dexes")
        read_seconds = time.perf_counter() - read_start

        assert total == n
        assert pages == (n + 99) // 100
        assert len(first) == 100
        # Loose guards: enough to catch an accidental full-table pull or a
        # pathological query, without being flaky on CI hardware.
        assert sync_seconds < 20.0, f"catalog sync too slow: {sync_seconds:.2f}s"
        assert read_seconds < 3.0, f"paginated reads too slow: {read_seconds:.2f}s"

    def test_re_sync_5000_is_noop_unchanged(self, session):
        catalog.sync_catalog(session, summaries(5000))
        start = time.perf_counter()
        stats = catalog.sync_catalog(session, summaries(5000))
        elapsed = time.perf_counter() - start
        assert stats.inserted == 0
        assert stats.updated == 0
        assert stats.unchanged == 5000
        assert stats.total_after == 5000
        # A steady-state re-sync rewrites no chain rows and stays fast.
        assert elapsed < 20.0
