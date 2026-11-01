"""DeFiScope AI - FastAPI entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, engine, init_db
from app.rag.ingest import load_index, reindex
from app.rag.service import RagService
from app.routers import alerts, auth, briefs, catalog, chat, dashboard, protocols
from app.security.seed import seed_demo_users
from app.services import cache
from app.services import catalog as catalog_service
from app.services import preseed as preseed_service
from app.services.protocols import ProtocolResearchService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("defiscope")


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
        timeout=get_settings().http_timeout_seconds,
        headers={"User-Agent": "DeFiScope-AI/0.1 (research tool)"},
    )
    app.state.research_service = ProtocolResearchService()
    init_db()
    _seed_accounts()

    # Chat RAG service. Hydrate synchronously from any persisted chunks so the
    # endpoint can answer (offline/lexical) from the first request, then refresh
    # docs + live evidence in the background once the warm-up pass has populated
    # the snapshots/alerts the evidence chunks are built from.
    app.state.rag_service = RagService()
    _seed_chat_index(app.state.rag_service)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: alerts_alert_run(app.state), "interval", minutes=30, id="monitor")
    scheduler.start()
    logger.info("Scheduler started (monitoring every 30 min)")

    # Warm the DB so the DB-first dashboard has data on first load, but do NOT
    # await it in the lifespan: the pass fans out to sequential DefiLlama HTTP
    # calls (up to minutes on a slow network) and blocking here would delay the
    # port binding and fail readiness probes. Run it as a background task; the
    # dashboard's live-fallback covers the brief window before it completes.
    app.state.warmup_task = asyncio.create_task(_warmup(app.state))
    app.state.ingest_task = asyncio.create_task(_ingest(app.state))
    app.state.catalog_task = asyncio.create_task(_catalog_sync(app.state))
    app.state.preseed_task = asyncio.create_task(_preseed(app.state, app.state.catalog_task))

    yield

    app.state.warmup_task.cancel()
    app.state.ingest_task.cancel()
    app.state.catalog_task.cancel()
    app.state.preseed_task.cancel()
    scheduler.shutdown(wait=False)
    await app.state.http.aclose()
    await cache.aclose()


async def _catalog_sync(state) -> None:
    """Populate the discovery catalog on startup (best-effort).

    This is a metadata-only directory read, run as its own background task so it
    never delays the port binding and never triggers the analytics crawl. Once
    the rows exist, any scores already captured by monitoring are folded in."""
    session = SessionLocal()
    try:
        await catalog_service.ensure_populated(session, state.research_service.client, state.http)
        folded = catalog_service.refresh_analysis_from_snapshots(session)
        if folded:
            # ensure_populated already retired the cache if it synced; a score
            # fold changes the risk columns too, so bump again when it touches.
            await cache.bump_version()
            logger.info("Folded %d monitored protocol(s) into the catalog", folded)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - never let catalog sync crash startup
        logger.warning("Startup catalog sync failed (reads serve an empty page): %s", exc)
    finally:
        session.close()


async def _preseed(state, catalog_task: asyncio.Task) -> None:
    """Warm detail pages by seeding the unmonitored catalog in bounded batches.

    Waits for the startup catalog sync first (the seed queue *is* the catalog,
    so draining it before it exists would just spin on an empty table) - even
    if that task failed, its exceptions are caught inside, and an empty/partial
    catalog simply means an empty/partial queue: nothing to seed until the next
    sync. Runs entirely off the event loop; cancelled with the lifespan."""
    try:
        await catalog_task
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - _catalog_sync swallows; this is belt & braces
        logger.warning("Catalog sync task failed; pre-seed proceeds with what exists")
    session = SessionLocal()
    try:
        await preseed_service.seed_loop(state.research_service, state.http, session)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - seeding must not crash the app
        logger.warning("Catalog pre-seed loop failed (detail pages stay gap-only): %s", exc)
    finally:
        session.close()


async def _warmup(state) -> None:
    try:
        await alerts_alert_run(state)
        logger.info("Startup warm-up pass complete")
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - never let warm-up crash the app
        logger.warning("Startup warm-up pass failed (will retry on demand): %s", exc)


def _seed_accounts() -> None:
    """Create the demo logins (no-op outside ``auth_mode == "demo"``).

    Best-effort: a seeding failure must not stop the service from starting - an
    operator can still log in with an account that already exists, and the
    reason is logged rather than swallowed."""
    session = SessionLocal()
    try:
        created = seed_demo_users(session)
        if created:
            logger.info("Seeded %d demo account(s) for auth_mode=demo", created)
    except Exception as exc:  # noqa: BLE001 - startup must not depend on this
        logger.warning("Demo account seeding failed: %s", type(exc).__name__)
    finally:
        session.close()


def _seed_chat_index(rag_service: RagService) -> None:
    """Best-effort cold-start hydration from persisted chunks (never blocks)."""
    session = SessionLocal()
    try:
        n = load_index(session, rag_service)
        if n:
            logger.info("Chat index hydrated from %d persisted chunks", n)
    except Exception as exc:  # noqa: BLE001 - empty index is a valid cold start
        logger.warning("Chat index hydration skipped: %s", type(exc).__name__)
    finally:
        session.close()


async def _ingest(state) -> None:
    # Wait for the warm-up pass so tracked protocols + recent alerts exist in
    # the DB - those rows are what the evidence chunks are derived from.
    try:
        await state.warmup_task
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - warmup already logged; still try to index
        pass
    session = SessionLocal()
    try:
        await reindex(session, state.research_service, state.http, state.rag_service)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - never let ingest crash the app
        logger.warning("Chat ingest failed (chat degrades to docs/refusal): %s", exc)
    finally:
        session.close()


app = FastAPI(
    title="DeFiScope AI",
    description="DeFi protocol research, explainable risk scoring and monitoring API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(protocols.router)
app.include_router(catalog.router)
app.include_router(briefs.router)
app.include_router(alerts.router)
app.include_router(dashboard.router)
app.include_router(chat.router)


def _db_status() -> str:
    """Cheap connectivity probe: 'ok' if the database answers SELECT 1."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 - report, never crash the probe
        logger.warning("DB health check failed: %s", exc)
        return "error"


@app.get("/api/health", tags=["meta"])
async def health():
    # Liveness: always 200 so a transient DB blip doesn't restart the container,
    # but surface the DB state for observability.
    return {"status": "ok", "db": _db_status(), "protocols": get_settings().protocol_slugs}


@app.get("/api/health/ready", tags=["meta"])
async def ready():
    # Readiness: 503 until the database is reachable, for compose/k8s probes.
    if _db_status() != "ok":
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ready"}
