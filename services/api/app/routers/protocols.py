"""Protocol research endpoints.

The list is *narrowed* to the subject's scope (a filtered list is the honest
answer to "what can I see"), while a single out-of-scope protocol is a 403:
silently returning `{}` or a 404 for a protocol that exists would be a lie the
UI cannot distinguish from a real absence.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.clients.defillama import DefiLlamaError
from app.db import get_session
from app.schemas import ProtocolOverview, ProtocolResearch
from app.security.deps import enforce, require
from app.security.policy import check_scope
from app.security.principal import Subject
from app.security.rbac import PROTOCOLS_READ
from app.services.protocols import ProtocolResearchService, pack_to_overview, pack_to_research

router = APIRouter(prefix="/api/protocols", tags=["protocols"])


def research_service(request: Request) -> ProtocolResearchService:
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def in_scope(subject: Subject, overview: ProtocolOverview) -> bool:
    """The ABAC predicate applied to a live DefiLlama overview."""
    return check_scope(
        subject,
        category=overview.category,
        chain=overview.top_chain,
        resource=overview.slug,
    ).allowed


@router.get("", response_model=list[ProtocolOverview])
async def list_protocols(
    request: Request,
    subject: Subject = Depends(require(PROTOCOLS_READ)),
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
):
    slugs = await svc.watchlist_slugs(http)
    packs = await svc.get_packs(slugs, http)
    if not packs:
        raise HTTPException(502, "Could not load any protocol data from DefiLlama")
    overviews = [pack_to_overview(p) for p in packs]
    return [o for o in overviews if in_scope(subject, o)]


@router.get("/{slug}", response_model=ProtocolResearch)
async def protocol_detail(
    slug: str,
    request: Request,
    subject: Subject = Depends(require(PROTOCOLS_READ)),
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(get_session),
):
    try:
        # The session is passed so the pack carries on-chain activity. That read
        # is DB-only (never a Dune call), which is what makes this endpoint
        # cost-free to open and immune to a Dune outage.
        pack = await svc.get_pack(slug, http, session=session)
    except DefiLlamaError as exc:
        raise HTTPException(404, str(exc)) from exc
    overview = pack_to_overview(pack)
    enforce(
        check_scope(
            subject,
            category=overview.category,
            chain=overview.top_chain,
            resource=f"'{slug}' ({overview.category or 'uncategorised'})",
        )
    )
    return pack_to_research(pack)
