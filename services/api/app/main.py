"""DeFiScope AI - FastAPI entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.routers import alerts, briefs, protocols
from app.services.protocols import ProtocolResearchService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("defiscope")

settings = get_settings()


async def alerts_alert_run(state) -> list:
    """Scheduled monitoring pass (also usable by manual triggers)."""
    from app.services import alerts as alert_engine

    session = SessionLocal()
    try:
        return await alert_engine.run_monitor(state.research_service, state.http, session)
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers={"User-Agent": "DeFiScope-AI/0.1 (research tool)"},
    )
    app.state.research_service = ProtocolResearchService()
    init_db()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: alerts_alert_run(app.state), "interval", minutes=30, id="monitor")
    scheduler.start()
    logger.info("Scheduler started (monitoring every 30 min)")

    yield

    scheduler.shutdown(wait=False)
    await app.state.http.aclose()


app = FastAPI(
    title="DeFiScope AI",
    description="DeFi protocol research, explainable risk scoring and monitoring API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(protocols.router)
app.include_router(briefs.router)
app.include_router(alerts.router)


@app.get("/api/health", tags=["meta"])
async def health():
    return {"status": "ok", "protocols": settings.protocol_slugs}
