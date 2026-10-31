"""Dashboard endpoints (DB-first reads with live hydration fallback).

Every route here is ``protocols:read``; the ABAC layer then narrows the answer
to the subject's data scope. The per-slug series routes are scope-checked
against the stored snapshot's attributes, so a slug cannot be *listed* out of
scope yet still be *queried* by URL.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import DashboardResponse, RiskPoint, TvlPoint
from app.security.deps import enforce, require
from app.security.policy import check_scope
from app.security.principal import Subject
from app.security.rbac import PROTOCOLS_READ
from app.services.dashboard import get_dashboard, history, latest_row_for, risk_history

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
