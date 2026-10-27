"""Protocol research endpoints."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.clients.defillama import DefiLlamaError
from app.config import get_settings
from app.schemas import ProtocolOverview, ProtocolResearch
from app.services.protocols import ProtocolResearchService, pack_to_overview, pack_to_research

router = APIRouter(prefix="/api/protocols", tags=["protocols"])


def research_service(request: Request) -> ProtocolResearchService:
    return request.app.state.research_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


@router.get("", response_model=list[ProtocolOverview])
async def list_protocols(
    request: Request,
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
):
    settings = get_settings()
    packs = await svc.get_packs(settings.protocol_slugs, http)
    if not packs:
        raise HTTPException(502, "Could not load any protocol data from DefiLlama")
    return [pack_to_overview(p) for p in packs]


@router.get("/{slug}", response_model=ProtocolResearch)
async def protocol_detail(
    slug: str,
    request: Request,
    svc: ProtocolResearchService = Depends(research_service),
    http: httpx.AsyncClient = Depends(http_client),
):
    try:
        pack = await svc.get_pack(slug, http)
    except DefiLlamaError as exc:
        raise HTTPException(404, str(exc)) from exc
    return pack_to_research(pack)
