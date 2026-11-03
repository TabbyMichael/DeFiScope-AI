"""Dashboard endpoints (DB-first reads with live hydration fallback).

Every route here is ``protocols:read``; the ABAC layer then narrows the answer
to the subject's data scope. The per-slug series routes are scope-checked
against the stored snapshot's attributes, so a slug cannot be *listed* out of
scope yet still be *queried* by URL.
"""

from __future__ import annotations

from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import (
    DashboardResponse,
    RiskPoint,
    TvlPoint,
    WatchlistPageResponse,
    WatchlistPageSize,
)
from app.security.deps import enforce, require
from app.security.policy import check_scope
from app.security.principal import Subject
from app.security.rbac import PROTOCOLS_READ
from app.services.dashboard import (
    SPARKLINE_DAYS,
    board_summary,
    get_dashboard,
    history,
    latest_row_for,
    latest_rows_paginated,
    risk_history,
    row_to_overview,
    sparklines,
    visible_slugs,
)

router = APIRouter(tags=["dashboard"])


def research_service(request: Request):
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def session_dep() -> Session:
    yield from get_session()


def _ensure_visible(session: Session, subject: Subject, slug: str) -> None:
    """403 when ``slug`` falls outside the subject's scope.

    A slug with no stored snapshot is allowed through: there is nothing to
    disclose yet, and the series routes answer with an empty list either way.
    """
    row = latest_row_for(session, slug)
    if row is None:
        return
    enforce(check_scope(subject, category=row.category, chain=row.top_chain, resource=f"'{slug}'"))


@router.get("/api/dashboard", response_model=DashboardResponse)
async def dashboard(
    request: Request,
    subject: Subject = Depends(require(PROTOCOLS_READ)),
    svc=Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(session_dep),
):
    """Latest snapshot per protocol + aggregate stats + alert feed, all read
    from the DB. Hydrates from DefiLlama only when the DB is empty/stale."""
    return await get_dashboard(svc, http, session, subject)


@router.get("/api/watchlist", response_model=WatchlistPageResponse)
async def watchlist(
    page: int = Query(1, ge=1, le=100_000, description="1-based page number"),
    size: WatchlistPageSize = Query(WatchlistPageSize.S_100, description="rows per page"),
    sort: Literal["risk", "tvl", "7d", "30d"] = Query("risk", description="sort column"),
    dir: Literal["asc", "desc"] = Query("desc", description="sort direction"),
    band: str | None = Query(None, max_length=40, description="filter by risk band"),
    q: str | None = Query(None, max_length=120, description="search name or slug"),
    subject: Subject = Depends(require(PROTOCOLS_READ)),
    session: Session = Depends(session_dep),
):
    """Market-wide risk watchlist, server-paginated over every monitored
    protocol (~5000) entirely in SQL - sorting, band filter, search and paging
    all happen server-side, so only one page of rows is ever serialized.

    The same ``protocols:read`` RBAC gate and ABAC ``scope`` narrowing as the
    dashboard are applied *in the query*, so ``total``, the page and the hero
    aggregates all reflect only what the caller may see - a scoped analyst can
    never bypass scope by URL to count or read rows they cannot open. The hero
    stats/band counts span the whole scoped board (not just this page); spark
    lines are fetched only for the returned page."""
    from app.services import alerts as alert_engine

    page_size = int(size)
    offset = (page - 1) * page_size
    rows, total = latest_rows_paginated(
        session,
        sort=sort,
        direction=dir,
        band=band,
        q=q,
        offset=offset,
        limit=page_size,
        scope=subject.scope,
    )
    items = [row_to_overview(r) for r in rows]
    series = sparklines(session, [p.slug for p in items], SPARKLINE_DAYS)
    for p in items:
        p.sparkline = series.get(p.slug, [])

    # Active-alert counts + withholding, scoped exactly as the dashboard does:
    # ``visible_slugs`` returns None for an unrestricted caller (cheap) and the
    # caller's slug set when restricted, so the board and the alert feed cannot
    # disagree about what is in scope.
    visible = visible_slugs(session, subject)
    today_alerts, withheld = alert_engine.today_alerts_for(
        session, subject, limit=200, visible_slugs=visible
    )
    stats, as_of = board_summary(session, scope=subject.scope, alerts=today_alerts)
    pages = (total + page_size - 1) // page_size if page_size else 0

    return WatchlistPageResponse(
        items=items,
        total=total,
        page=page,
        size=page_size,
        pages=pages,
        sort=sort,
        dir=dir,
        band=band,
        q=q,
        stats=stats,
        band_counts=stats.by_band,
        as_of=as_of,
        withheld=withheld,
    )


@router.get("/api/protocols/{slug}/history", response_model=list[TvlPoint])
async def protocol_history(
    slug: str,
    days: int = Query(30, ge=1, le=365, description="trailing daily points"),
    subject: Subject = Depends(require(PROTOCOLS_READ)),
    session: Session = Depends(session_dep),
):
    _ensure_visible(session, subject, slug)
    return history(session, slug, days)


@router.get("/api/protocols/{slug}/risk-history", response_model=list[RiskPoint])
async def protocol_risk_history(
    slug: str,
    days: int = Query(90, ge=1, le=365, description="trailing scored days"),
    subject: Subject = Depends(require(PROTOCOLS_READ)),
    session: Session = Depends(session_dep),
):
    """Daily composite risk-score trend for one protocol (DB read, no crawl).

    Only days the scheduler actually scored are returned, so the series reflects
    real observed risk rather than the null-scored DefiLlama backfill rows."""
    _ensure_visible(session, subject, slug)
    return risk_history(session, slug, days)
