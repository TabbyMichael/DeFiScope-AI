"""Research brief endpoints.

Reading a brief and downloading one are separate rights: a caveated document is
fine to read on screen, but exporting it turns it into a file someone will paste
into a deck. So ``briefs:export`` sits on top of ``briefs:read`` *and* the
confidence gate, which is why the export route can fail for a role that can see
the same brief perfectly well.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.clients.defillama import DefiLlamaError
from app.schemas import ResearchBrief
from app.security.deps import enforce, require
from app.security.policy import check_brief_export, check_scope
from app.security.principal import Subject
from app.security.rbac import BRIEFS_EXPORT, BRIEFS_READ
from app.services.briefs import build_brief
from app.services.export import VALID_FORMATS, render
from app.services.protocols import ProtocolResearchService, pack_to_overview

router = APIRouter(prefix="/api/briefs", tags=["briefs"])


def research_service(request: Request) -> ProtocolResearchService:
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def _enforce_scope(subject: Subject, pack, slug: str) -> None:
    """Briefs inherit the protocol's attributes - no separate policy."""
    overview = pack_to_overview(pack)
    enforce(
        check_scope(
            subject,
            category=overview.category,
            chain=overview.top_chain,
            resource=f"'{slug}' ({overview.category or 'uncategorised'})",
        )
    )


@router.get("/{slug}", response_model=ResearchBrief)
async def protocol_brief(
    slug: str,
    request: Request,
    subject: Subject = Depends(require(BRIEFS_READ)),
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
):
    try:
        pack = await svc.get_pack(slug, http)
    except DefiLlamaError as exc:
        raise HTTPException(404, str(exc)) from exc
    _enforce_scope(subject, pack, slug)
    return await build_brief(pack, http)


@router.get("/{slug}/export", response_class=Response)
async def export_brief(
    slug: str,
    request: Request,
    format: str = Query("md", description="download format: md | csv | pdf"),
    subject: Subject = Depends(require(BRIEFS_EXPORT)),
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
):
    """Render the brief for download as Markdown, CSV or PDF.

    Returns raw bytes with a ``Content-Disposition: attachment`` header so the
    browser saves the file. Unknown formats are a 400; an unfetchable protocol
    is a 404 (mirrors the JSON brief endpoint). The web app proxies this through
    a same-origin route handler so the compose-internal API URL stays server-side.

    The confidence gate is evaluated after the brief is composed because
    confidence is a property of the brief itself - there is no cheaper way to
    know it in advance. A denied export therefore costs the same generation as
    an allowed one; the cost ceiling for that lives in the deferred
    per-subject rate limiting, not here.
    """
    if format not in VALID_FORMATS:
        raise HTTPException(400, f"unsupported format {format!r}; expected one of {VALID_FORMATS}")
    try:
        pack = await svc.get_pack(slug, http)
    except DefiLlamaError as exc:
        raise HTTPException(404, str(exc)) from exc
    _enforce_scope(subject, pack, slug)
    brief = await build_brief(pack, http)
    enforce(
        check_brief_export(
            subject,
            confidence=brief.sections.confidence,
            data_gaps=brief.sections.data_gaps,
        )
    )
    payload, media_type, filename = render(brief, format)
    # RFC 5987 ``filename*`` carries the UTF-8 name for non-ASCII protocols; the
    # plain ``filename`` stays an ASCII fallback for older clients.
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=payload, media_type=media_type, headers={"Content-Disposition": disposition}
    )
