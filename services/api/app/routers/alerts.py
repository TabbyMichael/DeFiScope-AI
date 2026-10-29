"""Alerts & monitoring endpoints."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import AlertRecord, get_session
from app.schemas import Alert
from app.services import alerts as alert_engine
from app.services.protocols import ProtocolResearchService

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def research_service(request: Request) -> ProtocolResearchService:
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def session_dep() -> Session:
    yield from get_session()


@router.get("", response_model=list[Alert])
async def current_alerts(
    session: Session = Depends(session_dep),
    limit: int = 50,
):
    """Today's active alerts, served straight from the durable log.

    This is a fast DB read - it does NOT trigger a crawl. The scheduler and
    ``POST /api/alerts/run`` are the owners of the (expensive) DefiLlama
    monitoring pass that populates these rows."""
    rows = alert_engine.today_alerts(session, limit=limit)
    return sorted(rows, key=lambda a: (a.severity != "critical", a.triggered_at))


@router.post("/run", response_model=list[Alert])
async def run_alert_check(
    request: Request,
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(session_dep),
):
    """Manual/admin trigger for a full monitoring pass: crawl the watchlist,
    evaluate rules, persist alerts + daily snapshots, then return the alerts
    that fired on this pass (the same set ``GET /api/alerts`` will now serve)."""
    triggered = await alert_engine.run_monitor(svc, http, session)
    return sorted(triggered, key=lambda a: (a.severity != "critical", a.triggered_at))


@router.get("/history", response_model=list[Alert])
async def alert_history(session: Session = Depends(session_dep), limit: int = 100):
    rows = session.execute(
        select(AlertRecord).order_by(AlertRecord.triggered_at.desc()).limit(limit)
    ).scalars()
    return [
        Alert(
            id=r.id,
            slug=r.slug,
            protocol=r.protocol,
            rule=r.rule,
            severity=r.severity,
            message=r.message,
            evidence=r.evidence or {},
            triggered_at=r.triggered_at,
        )
        for r in rows
    ]
