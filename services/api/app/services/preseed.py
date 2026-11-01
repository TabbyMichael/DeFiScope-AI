"""Catalog pre-seed: bounded background crawl that makes detail pages rich.

The DB-first detail path answers from ``protocol_snapshots``; a protocol with no
snapshot yet is an honest gap-only page (catalog metadata, nulls). This service
removes those gaps *ahead of the first visit* by crawling the discovery catalog
in small, throttled batches and persisting the same snapshot rows a monitoring
pass writes - tagged ``monitored = 0``.

Two boundaries keep the pass safe:

* **The board is untouched.** Unmonitored rows are excluded from every
  dashboard aggregate and the staleness clock (see services/dashboard.py), so
  pre-seeded CEX/Bridge totals can neither distort board numbers nor keep a
  stale board looking fresh. No alerts are evaluated and nothing is notified -
  this pass exists purely to warm read models.
* **DefiLlama is respected.** Batches are capped by ``preseed_batch_size``,
  run through the existing ``crawl_concurrency`` semaphore, and pause
  ``preseed_batch_pause_seconds`` between batches, so ~9k protocols drain over
  hours rather than as one burst.
* **Interactive requests are never starved.** The whole app shares one uvicorn
  worker and one event loop. A full 150-protocol gather - plus the pandas
  parsing each pack goes through - monopolises that loop for seconds at a
  time, and anything arriving meanwhile (a login, say) queues until the web
  proxy gives up. So the crawl runs in ``preseed_chunk_size`` pieces with a
  pause between them, and the synchronous DB writes move to a worker thread
  (safe: this session belongs to the seed loop alone and nothing touches it
  while the thread runs).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import ProtocolCatalog, ProtocolSnapshot
from app.services import alerts as alert_engine
from app.services.protocols import ProtocolResearchService, ResearchPack, pack_to_overview

logger = logging.getLogger(__name__)


def unseeded_slugs(session: Session, limit: int, min_tvl: float = 0.0) -> list[str]:
    """Catalog slugs with no snapshot row yet, biggest first.

    An anti-join (``NOT IN`` the snapshot slugs, indexed by ``ix_snapshot_slug_date``
    leading with slug) rather than a correlated EXISTS - at a few thousand rows
    either plan is cheap, and this one reads plainly. Rows with a NULL TVL are
    skipped: a protocol DefiLlama does not even list a TVL for is not who the
    seed loop is for. ``min_tvl`` is the floor for the steady-state loop; the
    initial drain lowers it to sweep the tail once the big names are in.
    """
    seeded = select(ProtocolSnapshot.slug).scalar_subquery()
    stmt = (
        select(ProtocolCatalog.slug)
        .where(ProtocolCatalog.tvl.isnot(None), ProtocolCatalog.tvl >= min_tvl)
        .where(ProtocolCatalog.slug.not_in(seeded))
        .order_by(ProtocolCatalog.tvl.desc(), ProtocolCatalog.slug)
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


async def run_batch(
    svc: ProtocolResearchService,
    http,
    session: Session,
    limit: int | None = None,
    min_tvl: float | None = None,
) -> int:
    """Crawl one bounded batch of unseeded protocols and persist their
    snapshots as unmonitored (``monitored = 0``) rows. Returns the number of
    protocols captured.

    Deliberately *not* a monitoring pass: no alert rules, no notification
    fan-out. Scores are still folded into the catalog (so the Explorer's risk
    sort improves as the seed drains) and cached catalog pages are retired -
    the same guarded write ``run_monitor`` performs, and equally best-effort
    here: a catalog-refresh failure must not lose the snapshots just written.
    """
    settings = get_settings()
    batch = max(1, limit or settings.preseed_batch_size)
    floor = settings.preseed_min_tvl if min_tvl is None else min_tvl
    slugs = unseeded_slugs(session, batch, floor)
    if not slugs:
        return 0
    # Crawl in small chunks, yielding between them. One unbroken 150-protocol
    # gather (fetch + pandas) keeps the single event loop busy for seconds at a
    # stretch, and interactive requests queue behind it - the web login proxy
    # gives up after 15s. Chunk pauses keep that window short.
    chunk = max(1, settings.preseed_chunk_size)
    pause = max(0.0, settings.preseed_chunk_pause_seconds)
    packs: list[ResearchPack] = []
    for start in range(0, len(slugs), chunk):
        if start and pause:
            await asyncio.sleep(pause)
        # No session on the packs: on-chain activity is a detail-read concern
        # and this pass never renders a research payload - skip the extra DB
        # round-trips.
        packs.extend(await svc.get_packs(slugs[start : start + chunk], http))
    if not packs:
        return 0
    # The writes are synchronous SQLAlchemy over ~150 protocols x full TVL
    # history; run them in a worker thread so the loop stays free. The session
    # is the seed loop's own (main._preseed) and nothing else touches it while
    # this await is in flight. The fold's cache bump is a coroutine, so hand
    # the running loop to the thread and schedule onto it explicitly.
    await asyncio.to_thread(_write_packs, session, packs, asyncio.get_running_loop())
    logger.info("Pre-seed batch captured %d/%d protocol(s)", len(packs), len(slugs))
    return len(packs)


def _write_packs(
    session: Session, packs: list[ResearchPack], loop: asyncio.AbstractEventLoop
) -> None:
    """Persist one crawled batch: history backfill, latest-day snapshots, then
    the optional catalog-score fold. Runs in a worker thread (see run_batch)."""
    # Seed the full TVL history as unmonitored rows too - backfilled days feed
    # the same board aggregates as the latest row, so they must not be stamped
    # monitored=1 (the column default) or the guard below would only exclude
    # the single latest row and let every historical day leak onto the board.
    for pack in packs:
        alert_engine.backfill_history(session, pack, monitored=0)
    alert_engine.persist_snapshots(session, packs, monitored=0)
    # Same guarded catalog-score fold as run_monitor: the Explorer's risk sort
    # improves as the seed drains, and cached catalog pages are retired only if
    # the fold actually touched rows. Best-effort - a failure here must not
    # lose the snapshots persisted above.
    try:
        from app.services import cache, catalog

        overviews = [pack_to_overview(p) for p in packs]
        touched = catalog.refresh_analysis(
            session,
            [(p.slug, o.risk_score, o.risk_band) for p, o in zip(packs, overviews, strict=True)],
        )
        if touched:
            asyncio.run_coroutine_threadsafe(cache.bump_version(), loop)
    except Exception:  # noqa: BLE001 - catalog refresh is strictly optional
        logger.exception("Pre-seed catalog score refresh failed; snapshots kept")


async def seed_loop(svc: ProtocolResearchService, http, session: Session) -> None:
    """Drain the unseeded queue in bounded batches until it is empty.

    The TVL floor guides the initial climb (big names first); once nothing
    clears it, one last pass at floor 0 sweeps the tail if the operator kept
    ``preseed_backfill_rest`` on. A batch that crawls nothing (total DefiLlama
    outage: queue non-empty, zero packs captured) is retried after a longer
    pause so the loop cannot hot-spin against a dead upstream. Cancel-safe:
    shutdown interrupts between batches, never mid-write."""
    settings = get_settings()
    if not settings.preseed_enabled:
        return
    pause = max(1.0, settings.preseed_batch_pause_seconds)
    floor_done = False
    while True:
        captured = 0
        try:
            floor = 0.0 if floor_done else settings.preseed_min_tvl
            captured = await run_batch(svc, http, session, min_tvl=floor)
            # Re-check the queue at the *same* floor: a batch that crawled but
            # captured nothing (upstream outage) keeps the queue non-empty and
            # must retry, never advance to the tail sweep.
            queued = unseeded_slugs(session, 1, floor)
            if not queued:
                if floor_done or not settings.preseed_backfill_rest:
                    logger.info("Pre-seed queue drained; seed loop finished")
                    return
                floor_done = True
                logger.info("Pre-seed: TVL-floored queue done, sweeping the tail")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a bad batch must not kill the loop
            logger.warning("Pre-seed batch failed (%s); retrying after pause", type(exc).__name__)
        # Progress: the cadence pause. No progress: triple it, so a dead
        # upstream costs patience rather than a hot retry spin.
        await asyncio.sleep(pause if captured else pause * 3)
