"""Dashboard endpoints (DB-first reads with live hydration fallback)."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import DashboardResponse, RiskPoint, TvlPoint
from app.services.dashboard import get_dashboard, history, risk_history

router = APIRouter(tags=["dashboard"])


def research_service(request: Request):
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def session_dep() -> Session:
    yield from get_session()


@router.get("/api/dashboard", response_model=DashboardResponse)
async def dashboard(
    request: Request,
    svc=Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(session_dep),
):
    """Latest snapshot per protocol + aggregate stats + alert feed, all read
    from the DB. Hydrates from DefiLlama only when the DB is empty/stale."""
    return await get_dashboard(svc, http, session)


@router.get("/api/protocols/{slug}/history", response_model=list[TvlPoint])
async def protocol_history(
    slug: str,
    days: int = Query(30, ge=1, le=365, description="trailing daily points"),
    session: Session = Depends(session_dep),
):
    return history(session, slug, days)


@router.get("/api/protocols/{slug}/risk-history", response_model=list[RiskPoint])
async def protocol_risk_history(
    slug: str,
    days: int = Query(90, ge=1, le=365, description="trailing scored days"),
    session: Session = Depends(session_dep),
):
    """Daily composite risk-score trend for one protocol (DB read, no crawl).

    Only days the scheduler actually scored are returned, so the series reflects
    real observed risk rather than the null-scored DefiLlama backfill rows."""
    return risk_history(session, slug, days)
