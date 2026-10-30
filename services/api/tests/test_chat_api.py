"""Chat API contract tests: POST /api/chat and WS /ws/chat.

Run offline (no OpenAI key) so the deterministic extractive path is what the
transports expose. Lifespan is intentionally not started; we wire the exact app
state the endpoints depend on (rag_service + http), mirroring the pattern in
``test_api.py``.
"""

from __future__ import annotations

import httpx
import pytest
from app.db import init_db
from app.main import app
from app.rag.chunking import Chunk, content_hash
from app.rag.service import RagService
from fastapi.testclient import TestClient


def _service() -> RagService:
    svc = RagService()
    texts = [
        "Real yield is the share of TVL growth backed by fees rather than emissions.",
        "The depeg watch flags stablecoins drifting from their one dollar peg.",
    ]
    svc.index(
        [
            Chunk(
                id=content_hash(t),
                doc_id="doc:Methodology",
                section="Sec",
                text=t,
                source_type="doc",
                source_name="Methodology",
                protocol_slug=None,
            )
            for t in texts
        ]
    )
    return svc


@pytest.fixture()
def wired():
    init_db()
    app.state.rag_service = _service()
    app.state.http = httpx.AsyncClient()
    yield
    # No LLM/embedding call is made offline, so the client never bound a loop.


async def test_post_chat_returns_grounded_extractive_answer(wired):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/chat", json={"question": "real yield fees emissions"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["grounded"] is True
    assert data["generated_by"] == "extractive"
    assert data["citations"][0]["source"] == "Methodology"


async def test_post_chat_validation_requires_question(wired):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/chat", json={"question": ""})
    assert resp.status_code == 422


def test_ws_chat_streams_frames(wired):
    client = TestClient(app)  # no context manager => lifespan (and warm-up) not run
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"question": "what is real yield fees emissions"})
        frames: list[dict] = []
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame["type"] in ("done", "error"):
                break
    types = [f["type"] for f in frames]
    assert "token" in types and types[-1] == "done"
    assert frames[-1]["answer"]["grounded"] is True


def test_ws_chat_rejects_empty_and_bad_frames(wired):
    client = TestClient(app)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"question": "   "})
        assert ws.receive_json()["type"] == "error"
        # a real question still works on the same socket afterwards
        ws.send_json({"question": "stablecoin depeg peg dollar"})
        got = []
        while True:
            frame = ws.receive_json()
            got.append(frame["type"])
            if frame["type"] in ("done", "error"):
                break
    assert "done" in got


def test_ws_chat_denies_disallowed_origin(wired):
    # Unit-test the gate directly rather than relying on a close-before-accept
    # socket (whose exception type varies across Starlette versions).
    from app.config import get_settings
    from app.routers.chat import _origin_allowed

    allow = get_settings().cors_origin_list[0]
    assert _origin_allowed(None) is True  # non-browser client
    assert _origin_allowed(allow) is True
    assert _origin_allowed("http://evil.example") is False
