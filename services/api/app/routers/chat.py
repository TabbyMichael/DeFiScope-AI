"""Ask-the-analyst chat endpoints (roadmap #8).

Two transports for the same grounded engine:
- ``POST /api/chat`` - a single request/response, trivially testable and the
  fallback when a WebSocket can't be established (locked-down networks).
- ``WS /ws/chat`` - streams token/citations/done frames so the UI renders the
  answer as it composes. Cloudflare quick tunnels support WebSocket (but not
  SSE), which is why streaming rides on WS rather than server-sent events.

Both return the identical ``ChatAnswer`` shape with ``citations`` + ``grounded``
+ ``generated_by`` so a model answer is never mistaken for verified fact.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.rag.service import RagService
from app.schemas import ChatAnswer, ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Keep the tunnel's idle timeout from dropping a quiet socket mid-generation.
WS_PING_SECONDS = 25


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
    svc: RagService = Depends(rag_service),
    http: httpx.AsyncClient = Depends(http_client),
):
    try:
        return await svc.answer(body.question, http, protocol_slug=body.protocol_slug)
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


@router.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    if not _origin_allowed(ws.headers.get("origin")):
        await ws.close(code=1008)  # policy violation
        return
    await ws.accept()
    svc: RagService = ws.app.state.rag_service
    http: httpx.AsyncClient = ws.app.state.http
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
            try:
                async for frame in svc.answer_stream(question, http, protocol_slug=protocol_slug):
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
