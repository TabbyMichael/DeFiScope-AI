"""Research brief endpoints."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.clients.defillama import DefiLlamaError
from app.schemas import ResearchBrief
from app.services.briefs import build_brief
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
