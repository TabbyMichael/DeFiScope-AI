"""Public status endpoint.

Deliberately unauthenticated and aggregate-only. The dashboard, protocol and
alert routes require a subject because they disclose row-level data; this one
answers "how much has this service observed, and as of when", which is the
information a prospective operator needs before signing in, and the same
information the landing page renders as proof that the numbers are real.

Scope is therefore limited to counts and configuration booleans. No protocol
name, no TVL figure, no alert text and no secret crosses this boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import CoverageStatus
from app.services.status import coverage

router = APIRouter(tags=["meta"])


def session_dep() -> Session:
    yield from get_session()


@router.get("/api/status", response_model=CoverageStatus)
async def status(session: Session = Depends(session_dep)):
    """Aggregate coverage of the store: protocols, days, bands, alerts, index."""
    return coverage(session)
