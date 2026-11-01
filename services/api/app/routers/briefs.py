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
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import ResearchBrief
from app.security.deps import enforce, require
from app.security.policy import check_brief_export, check_scope
from app.security.principal import Subject
from app.security.rbac import BRIEFS_EXPORT, BRIEFS_READ
from app.services import detail
from app.services.briefs import build_brief
from app.services.export import VALID_FORMATS, render

router = APIRouter(prefix="/api/briefs", tags=["briefs"])


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def _load_or_404(slug: str, session: Session) -> detail.DetailPack:
    """DB-first brief source: the same pack the detail page renders. A slug with
    neither a snapshot nor a catalog row is a genuine 404; a listed-but-uncaptured
    slug loads with gap fields and the template brief states them."""
    try:
        return detail.load_detail(session, slug)
    except detail.ProtocolUnknown as exc:
        raise HTTPException(404, f"unknown protocol '{exc.args[0]}'") from exc


def _enforce_scope(subject: Subject, dp: detail.DetailPack, slug: str) -> None:
    """Briefs inherit the protocol's attributes - no separate policy."""
    enforce(
        check_scope(
            subject,
            category=dp.overview.category,
            chain=dp.overview.top_chain,
            resource=f"'{slug}' ({dp.overview.category or 'uncategorised'})",
        )
    )


@router.get("/{slug}", response_model=ResearchBrief)
async def protocol_brief(
    slug: str,
    subject: Subject = Depends(require(BRIEFS_READ)),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(get_session),
):
    dp = _load_or_404(slug, session)
    _enforce_scope(subject, dp, slug)
    return await build_brief(dp, http)


@router.get("/{slug}/export", response_class=Response)
async def export_brief(
    slug: str,
    format: str = Query("md", description="download format: md | csv | pdf"),
    subject: Subject = Depends(require(BRIEFS_EXPORT)),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(get_session),
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
    dp = _load_or_404(slug, session)
    _enforce_scope(subject, dp, slug)
    brief = await build_brief(dp, http)
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
