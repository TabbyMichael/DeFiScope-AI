"""Research brief endpoints."""

from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.clients.defillama import DefiLlamaError
from app.schemas import ResearchBrief
from app.services.briefs import build_brief
from app.services.export import VALID_FORMATS, render
from app.services.protocols import ProtocolResearchService

router = APIRouter(prefix="/api/briefs", tags=["briefs"])


def research_service(request: Request) -> ProtocolResearchService:
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


@router.get("/{slug}", response_model=ResearchBrief)
async def protocol_brief(
    slug: str,
    request: Request,
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
):
    try:
        pack = await svc.get_pack(slug, http)
    except DefiLlamaError as exc:
        raise HTTPException(404, str(exc)) from exc
    return await build_brief(pack, http)


@router.get("/{slug}/export", response_class=Response)
async def export_brief(
    slug: str,
    request: Request,
    format: str = Query("md", description="download format: md | csv | pdf"),
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
):
    """Render the brief for download as Markdown, CSV or PDF.

    Returns raw bytes with a ``Content-Disposition: attachment`` header so the
    browser saves the file. Unknown formats are a 400; an unfetchable protocol
    is a 404 (mirrors the JSON brief endpoint). The web app proxies this through
    a same-origin route handler so the compose-internal API URL stays server-side.
    """
    if format not in VALID_FORMATS:
        raise HTTPException(400, f"unsupported format {format!r}; expected one of {VALID_FORMATS}")
    try:
        pack = await svc.get_pack(slug, http)
    except DefiLlamaError as exc:
        raise HTTPException(404, str(exc)) from exc
    brief = await build_brief(pack, http)
    payload, media_type, filename = render(brief, format)
    # RFC 5987 ``filename*`` carries the UTF-8 name for non-ASCII protocols; the
    # plain ``filename`` stays an ASCII fallback for older clients.
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=payload, media_type=media_type, headers={"Content-Disposition": disposition}
    )
