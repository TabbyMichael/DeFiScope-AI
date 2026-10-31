"""Ask-the-analyst chat endpoints (roadmap #8).

Two transports for the same grounded engine:
- ``POST /api/chat`` - a single request/response, trivially testable and the
  fallback when a WebSocket can't be established (locked-down networks).
- ``WS /ws/chat`` - streams token/citations/done frames so the UI renders the
  answer as it composes. Cloudflare quick tunnels support WebSocket (but not
  SSE), which is why streaming rides on WS rather than server-sent events.

Both return the identical ``ChatAnswer`` shape with ``citations`` + ``grounded``
+ ``generated_by`` so a model answer is never mistaken for verified fact.

Authorization differs by transport because the constraints do:

- ``POST /api/chat`` rides the normal request path, so the bearer token works and
  the router can resolve the subject like any other route.
- ``WS /ws/chat`` is opened *by the browser* against the API host, where the web
  app's httpOnly cookie does not travel. The client therefore exchanges its
  session for a 60-second single-use ticket (``POST /api/auth/ticket``) and
  passes it as ``?ticket=``. The ticket is redeemed exactly once, before
  ``accept()``, so an unauthenticated socket never gets a handshake.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_session
from app.rag.service import RagService
from app.schemas import ChatAnswer, ChatRequest
from app.security import sessions
from app.security.deps import enforce, require
from app.security.policy import check_scope
from app.security.principal import ANONYMOUS, Subject
from app.security.rbac import CHAT_ASK, has_permission
from app.services.dashboard import latest_row_for, visible_slugs

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Keep the tunnel's idle timeout from dropping a quiet socket mid-generation.
WS_PING_SECONDS = 25
# Close code used for every socket-level authorization failure. Deliberately the
# same value for "no ticket" and "bad ticket" so the socket is not an oracle.
WS_POLICY_VIOLATION = 1008


def rag_service(request: Request) -> RagService:
    return request.app.state.rag_service


def http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def _origin_allowed(origin: str | None) -> bool:
    # No Origin header = non-browser client (tests, curl, the Next server):
    # allowed. A browser always sends one, so a present-but-unlisted origin is
    # rejected - the WS analogue of the app's CORS allow-list.
    if not origin:
        return True
    return origin in get_settings().cors_origin_list


@router.post("/api/chat", response_model=ChatAnswer)
async def chat(
    body: ChatRequest,
    subject: Subject = Depends(require(CHAT_ASK)),
    svc: RagService = Depends(rag_service),
    http: httpx.AsyncClient = Depends(http_client),
    session: Session = Depends(get_session),
):
    allowed = visible_slugs(session, subject)
    if body.protocol_slug and allowed is not None:
        # Scope-check the *named* protocol through its stored attributes so the
        # reason names the failing axis, then keep the whole answer scoped.
        row = latest_row_for(session, body.protocol_slug)
        if row is None or body.protocol_slug not in allowed:
            enforce(
                check_scope(
                    subject,
                    category=row.category if row else None,
                    chain=row.top_chain if row else None,
                    resource=f"'{body.protocol_slug}'",
                )
            )
    try:
        return await svc.answer(
            body.question, http, protocol_slug=body.protocol_slug, visible_slugs=allowed
        )
    except Exception as exc:  # noqa: BLE001 - a chat failure is a 502, not a crash
        logger.warning("Chat request failed: %s", type(exc).__name__)
        raise HTTPException(502, "chat unavailable") from exc


async def _ping_loop(ws: WebSocket, send_lock: asyncio.Lock) -> None:
    """Periodically nudge the socket so an idle proxy/tunnel keeps it alive."""
    try:
        while True:
            await asyncio.sleep(WS_PING_SECONDS)
            async with send_lock:
                await ws.send_json({"type": "ping"})
    except (asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
        pass


def _socket_subject(ws: WebSocket) -> Subject | None:
    """Resolve the socket's identity, or None when it must be refused.

    ``auth_mode == "off"`` keeps the legacy open socket. Otherwise the ticket is
    redeemed (single use) and the role must still hold ``chat:ask`` - a ticket
    issues a session, it does not grant a verb.
    """
    if get_settings().auth_mode == "off":
        return ANONYMOUS
    subject = sessions.tickets.redeem(ws.query_params.get("ticket"))
    if subject is None or not has_permission(subject, CHAT_ASK):
        return None
    return subject


@router.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    if not _origin_allowed(ws.headers.get("origin")):
        await ws.close(code=WS_POLICY_VIOLATION)
        return
    subject = _socket_subject(ws)
    if subject is None:
        await ws.close(code=WS_POLICY_VIOLATION)
        return
    await ws.accept()
    svc: RagService = ws.app.state.rag_service
    http: httpx.AsyncClient = ws.app.state.http

    # Resolved once per socket: the scope it carries is a property of the session
    # that opened it, and a socket outliving a role change is closed by expiry.
    db = SessionLocal()
    try:
        allowed = visible_slugs(db, subject)
    finally:
        db.close()

    send_lock = asyncio.Lock()
    ping_task = asyncio.create_task(_ping_loop(ws, send_lock))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
                question = str(payload.get("question", "")).strip()
                protocol_slug = payload.get("protocol_slug")
            except (json.JSONDecodeError, AttributeError):
                async with send_lock:
                    await ws.send_json({"type": "error", "message": "invalid JSON frame"})
                continue
            if not question:
                async with send_lock:
                    await ws.send_json({"type": "error", "message": "question is required"})
                continue
            if protocol_slug and allowed is not None and protocol_slug not in allowed:
                async with send_lock:
                    await ws.send_json(
                        {"type": "error", "message": "That protocol is outside your data scope."}
                    )
                continue
            try:
                async for frame in svc.answer_stream(
                    question, http, protocol_slug=protocol_slug, visible_slugs=allowed
                ):
                    async with send_lock:
                        await ws.send_json(frame)
            except Exception as exc:  # noqa: BLE001 - keep the socket alive
                logger.warning("Chat stream failed: %s", type(exc).__name__)
                async with send_lock:
                    await ws.send_json({"type": "error", "message": "generation failed"})
    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()
