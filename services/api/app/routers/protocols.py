"""Protocol catalog and research endpoints.

``GET /api/protocols`` now reads the *discovery catalog* from the database with
server-side pagination, search, filtering and sorting - the 5,000+ protocol
browsing surface. It never crawls per request on a warm catalog; a cold catalog
is filled with a single metadata sync (never an analytics crawl) as a fallback.

The detail route is DB-first: opening one protocol assembles its research
payload from persisted snapshots/catalog (never a live crawl), so a cold slug is
as fast as a warm one. The list is *narrowed* to the subject's scope (a filtered
page is the honest answer to "what can I see"), while a single out-of-scope
protocol is a 403 - silently returning nothing for a protocol that exists would
be a lie the UI cannot distinguish from a real absence.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.schemas import (
    CatalogFacets,
    CatalogPageSize,
    ProtocolCatalogPage,
    ProtocolResearch,
)
from app.security.deps import enforce, require
from app.security.policy import check_scope
from app.security.principal import Subject
from app.security.rbac import PROTOCOLS_READ
from app.services import cache, catalog, detail
from app.services.protocols import ProtocolResearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/protocols", tags=["protocols"])

# Longest search term accepted, so a stray paste cannot build a pathological LIKE
# over the whole table. Read once at import so FastAPI can bake it into OpenAPI.
_SEARCH_MAX_LEN = get_settings().catalog_search_max_length


def research_service(request: Request) -> ProtocolResearchService:
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


async def _ensure_catalog(session: Session, svc: ProtocolResearchService, http) -> None:
    """Best-effort cold-start fill from the DefiLlama directory.

    Delegates to ``catalog.ensure_populated`` (which short-circuits on a warm
    catalog and holds the shared fill lock). Any failure is swallowed here: an
    empty page is a valid, honest answer while discovery is unavailable."""
    try:
        await catalog.ensure_populated(session, svc.client, http)
    except Exception as exc:  # noqa: BLE001 - discovery outage degrades to empty
        logger.warning("Catalog cold-start sync skipped: %s", type(exc).__name__)


@router.get("", response_model=ProtocolCatalogPage)
async def list_protocols(
    request: Request,
    page: int = Query(1, ge=1, le=100_000, description="1-based page number"),
    page_size: CatalogPageSize = Query(CatalogPageSize.S_25, description="rows per page"),
    q: str | None = Query(None, max_length=_SEARCH_MAX_LEN, description="search name or slug"),
    chain: str | None = Query(None, max_length=80, description="filter by chain"),
    category: str | None = Query(None, max_length=80, description="filter by category"),
    band: str | None = Query(None, max_length=40, description="filter by risk band"),
    sort: Literal["tvl", "name", "updated", "risk"] = Query("tvl"),
    order: Literal["asc", "desc"] = Query("desc"),
    subject: Subject = Depends(require(PROTOCOLS_READ)),
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(get_session),
):
    """Paginated protocol discovery catalog, served entirely from the DB.

    Pagination, search, filtering and sorting all happen server-side; only one
    page of rows is ever returned. ``sort`` is bound to an allowlisted column
    (see ``catalog.SORT_COLUMNS``) - the caller's string never reaches SQL as
    text - and ordering is made deterministic with a slug tiebreak.

    A successful page is cached in Redis (when configured) keyed by the query
    *and* the caller's scope; a cache hit skips the cold-start check, both
    ``COUNT``s and the paged scan. With no Redis set every cache helper no-ops
    and this is exactly the uncached DB read it was before."""
    settings = get_settings()
    version = await cache.get_version()
    key = cache.catalog_page_key(
        version,
        q=q,
        chain=chain,
        category=category,
        band=band,
        sort=sort,
        order=order,
        page=page,
        page_size=int(page_size),
        scope=subject.scope,
    )
    hit = await cache.get_json(key)
    if hit is not None:
        return ProtocolCatalogPage.model_validate(hit)

    # Cold page. Let one in-flight request populate it; a concurrent sibling on
    # the same key waits briefly for that result instead of stampeding the DB
    # (a real effect even on one worker, since async requests interleave). When
    # caching is off ``try_lock`` always returns True, so this is the plain path.
    locked = await cache.try_lock(key)
    if not locked:
        for _ in range(3):
            await asyncio.sleep(0.15)
            hit = await cache.get_json(key)
            if hit is not None:
                return ProtocolCatalogPage.model_validate(hit)

    await _ensure_catalog(session, svc, http)
    items, total, pages = catalog.query_catalog(
        session,
        q=q,
        chain=chain,
        category=category,
        band=band,
        sort=sort,
        order=order,
        page=page,
        page_size=int(page_size),
        scope=subject.scope,
    )
    result = ProtocolCatalogPage(
        items=items,
        total=total,
        page=page,
        page_size=int(page_size),
        pages=pages,
        sort=sort,
        order=order,
        q=q.strip() or None if q else None,
        chain=chain,
        category=category,
        band=band.strip() or None if band else None,
    )
    # Only a *successful* result is stored; if the query raised we never get here.
    await cache.set_json(key, result.model_dump(mode="json"), settings.catalog_cache_ttl_seconds)
    if locked:
        await cache.release_lock(key)
    return result


@router.get("/facets", response_model=CatalogFacets)
async def protocol_facets(
    subject: Subject = Depends(require(PROTOCOLS_READ)),
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(get_session),
):
    """Distinct chain and category values present in the catalog, for the
    Explorer's filter selectors. Declared before ``/{slug}`` so "facets" is not
    swallowed as a protocol slug.

    Cached in Redis (when configured) by the catalog version; a hit skips the
    cold-start check and the two distinct scans. Uncached/faulted reads degrade
    to the current database path unchanged."""
    version = await cache.get_version()
    key = cache.facets_key(version)
    hit = await cache.get_json(key)
    if hit is not None:
        return CatalogFacets.model_validate(hit)
    await _ensure_catalog(session, svc, http)
    facets = catalog.catalog_facets(session)
    await cache.set_json(key, facets.model_dump(mode="json"), get_settings().facets_cache_ttl_seconds)
    return facets


@router.get("/{slug}", response_model=ProtocolResearch)
async def protocol_detail(
    slug: str,
    subject: Subject = Depends(require(PROTOCOLS_READ)),
    session: Session = Depends(get_session),
):
    """One protocol's research payload, assembled entirely from the DB.

    No longer a live DefiLlama crawl: the monitoring/pre-seed pass persists every
    field this renders, so opening a page is an indexed row read (sub-20ms) and a
    DefiLlama outage cannot slow it. A listed-but-uncaptured slug returns the
    catalog header with analysis fields as honest gaps; a slug with no catalog
    row *and* no snapshot is a genuine 404. Scope is enforced against the loaded
    row's category/chain exactly as the crawl path did, so a slug can never be
    opened out of scope nor hidden in scope."""
    try:
        pack = detail.load_detail(session, slug)
    except detail.ProtocolUnknown as exc:
        raise HTTPException(404, f"unknown protocol '{exc.args[0]}'") from exc
    overview = pack.overview
    enforce(
        check_scope(
            subject,
            category=overview.category,
            chain=overview.top_chain,
            resource=f"'{slug}' ({overview.category or 'uncategorised'})",
        )
    )
    return detail.to_research(pack)
