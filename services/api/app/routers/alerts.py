"""Alerts & monitoring endpoints.

Two distinct rights live here and they are deliberately not the same verb:
reading the alert feed (``alerts:read``) and spending compute on a crawl
(``monitor:run``). The read path is additionally narrowed twice - by data scope
and by clearance - and always reports how many rows the clearance gate removed.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import AlertRecord, get_session
from app.schemas import Alert
from app.security.deps import enforce, require
from app.security.policy import (
    check_monitor_freshness,
    check_monitor_hours,
    first_denial,
    split_visible_alerts,
)
from app.security.principal import Subject
from app.security.rbac import ALERTS_READ, MONITOR_RUN
from app.services import alerts as alert_engine
from app.services.dashboard import freshness_hours, visible_slugs
from app.services.protocols import ProtocolResearchService

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# Name of the header carrying the withheld count. A header rather than a wrapper
# object keeps the response a plain array, so no existing consumer breaks.
WITHHELD_HEADER = "X-Withheld-Alerts"


def research_service(request: Request) -> ProtocolResearchService:
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def session_dep() -> Session:
    yield from get_session()


@router.get("", response_model=list[Alert])
async def current_alerts(
    response: Response,
    subject: Subject = Depends(require(ALERTS_READ)),
    session: Session = Depends(session_dep),
    limit: int = 50,
):
    """Today's active alerts, served straight from the durable log.

    This is a fast DB read - it does NOT trigger a crawl. The scheduler and
    ``POST /api/alerts/run`` are the owners of the (expensive) DefiLlama
    monitoring pass that populates these rows.

    Critical alerts above the caller's clearance are withheld from the body and
    counted in ``X-Withheld-Alerts``: the reader still learns that something
    broke, without learning what."""
    rows, withheld = alert_engine.today_alerts_for(
        session, subject, limit=limit, visible_slugs=visible_slugs(session, subject)
    )
    response.headers[WITHHELD_HEADER] = str(withheld)
    return sorted(rows, key=lambda a: (a.severity != "critical", a.triggered_at))


@router.post("/run", response_model=list[Alert])
async def run_alert_check(
    response: Response,
    subject: Subject = Depends(require(MONITOR_RUN)),
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(session_dep),
):
    """Manual trigger for a full monitoring pass: crawl the watchlist,
    evaluate rules, persist alerts + daily snapshots, then return the alerts
    that fired on this pass (the same set ``GET /api/alerts`` will now serve).

    Gated twice beyond the role: a pass outside business hours is refused, and a
    pass over a *fresh* snapshot is refused as redundant - a crawl that cannot
    change anything is wasted upstream quota, not diligence. Both denials come
    back as an explanation rather than a bare 403."""
    denial = first_denial(
        check_monitor_hours(subject),
        check_monitor_freshness(subject, freshness_hours=freshness_hours(session)),
    )
    if denial is not None:
        enforce(denial)

    triggered = await alert_engine.run_monitor(svc, http, session)
    visible, withheld = split_visible_alerts(
        triggered, subject, visible_slugs=visible_slugs(session, subject)
    )
    response.headers[WITHHELD_HEADER] = str(withheld)
    return sorted(visible, key=lambda a: (a.severity != "critical", a.triggered_at))


@router.get("/history", response_model=list[Alert])
async def alert_history(
    response: Response,
    subject: Subject = Depends(require(ALERTS_READ)),
    session: Session = Depends(session_dep),
    limit: int = 100,
):
    rows = session.execute(
        select(AlertRecord).order_by(AlertRecord.triggered_at.desc()).limit(limit)
    ).scalars()
    alerts = [
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
    visible, withheld = split_visible_alerts(
        alerts, subject, visible_slugs=visible_slugs(session, subject)
    )
    response.headers[WITHHELD_HEADER] = str(withheld)
    return visible
