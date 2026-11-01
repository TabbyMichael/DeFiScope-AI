"""Catalog synchronization endpoints (discovery, distinct from monitoring).

``POST /api/catalog/sync`` refreshes the ``protocol_catalog`` table from the
DefiLlama directory. It is gated by ``monitor:run`` because it spends upstream
compute and mutates shared state, but it is *not* the analytics crawl: it makes a
single ``/protocols`` metadata read and performs no per-protocol detail, fees or
Dune work, so it can never widen the monitored set or consume a Dune budget.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import CatalogSyncStats
from app.security.deps import require
from app.security.principal import Subject
from app.security.rbac import MONITOR_RUN
from app.services import catalog
from app.services.protocols import ProtocolResearchService

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def research_service(request: Request) -> ProtocolResearchService:
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


@router.post("/sync", response_model=CatalogSyncStats)
async def sync_catalog(
    subject: Subject = Depends(require(MONITOR_RUN)),
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(get_session),
):
    """Idempotently upsert the full DefiLlama directory into the catalog.

    Returns per-outcome counters (inserted / updated / unchanged / skipped /
    duplicates) so an operator can see the sync did not lose or duplicate rows.
    Re-running it is safe: existing rows are updated in place and rows the
    provider no longer lists are left untouched."""
    return await catalog.sync_from_source(session, svc.client, http)
