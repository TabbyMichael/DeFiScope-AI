"""DB-first dashboard reads.

The board renders from `protocol_snapshots` / `alert_records`. Only when the
DB is empty or its newest capture is stale do we run a live monitoring pass
(which also backfills history), so normal dashboard loads never hit
DefiLlama directly.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.db import AlertRecord, ProtocolSnapshot
from app.schemas import (
    Alert,
    DashboardResponse,
    DashboardStats,
    Mover,
    ProtocolOverview,
    TvlPoint,
)

# If the newest capture is older than this, treat the board as stale and run a
# live hydration pass. The scheduler captures every 30 min, so this only
# triggers when the service has been down / freshly (re)started.
STALE_AFTER = timedelta(hours=6)

# Trailing window (days) for the inline sparkline attached to each row.
SPARKLINE_DAYS = 30

# Serializes concurrent live-hydration passes so a burst of dashboard requests
# on a cold DB triggers a single DefiLlama crawl rather than N of them.
_hydration_lock = asyncio.Lock()


def _snapshot_age_days(row_date: str | None) -> int:
    """Days between a snapshot's observation date and today. A row captured
    days ago should not masquerade as current even if its stored ``stale_days``
    was computed when DefiLlama was fresh."""
    if not row_date:
        return 0
    try:
        return max(0, (date.today() - date.fromisoformat(row_date)).days)
    except ValueError:
        return 0


def row_to_overview(r: ProtocolSnapshot) -> ProtocolOverview:
    # Surface genuine staleness: report whichever is larger, the age recorded
    # at capture time or the age of the snapshot itself relative to today.
    stale_days = max(r.stale_days or 0, _snapshot_age_days(r.date))
    return ProtocolOverview(
        slug=r.slug,
        name=r.name or r.slug,
        category=r.category,
        tvl=r.tvl,
        change_7d=r.change_7d,
        change_30d=r.change_30d,
        volatility_30d=r.volatility_30d,
        top_chain=r.top_chain,
        top_chain_share=r.top_chain_share,
        incentive_ratio=r.incentive_ratio,
        risk_score=r.risk_score,
        risk_band=r.risk_band or "unknown",
        stale_days=stale_days,
        source="db",
        as_of=r.date,
    )


def latest_rows(session: Session) -> list[ProtocolSnapshot]:
    """Newest snapshot per slug via a max(date) group-by joined back.

    The join can theoretically return more than one row per slug if duplicate
    (slug, date) rows exist (e.g. from a pre-unique-constraint database or a
    concurrent write), so we keep exactly one per slug here as a safety net."""
    sub = (
        session.query(
            ProtocolSnapshot.slug,
            func.max(ProtocolSnapshot.date).label("max_date"),
        )
        .group_by(ProtocolSnapshot.slug)
        .subquery()
    )
    rows = (
        session.query(ProtocolSnapshot)
        .join(
            sub,
            and_(
                ProtocolSnapshot.slug == sub.c.slug,
                ProtocolSnapshot.date == sub.c.max_date,
            ),
        )
        .order_by(ProtocolSnapshot.tvl.desc())
        .all()
    )
    by_slug: dict[str, ProtocolSnapshot] = {}
    for r in rows:
        if r.slug not in by_slug:
            by_slug[r.slug] = r
    return list(by_slug.values())


def sparklines(session: Session, slugs: list[str], days: int = SPARKLINE_DAYS) -> dict[str, list[TvlPoint]]:
    """Trailing daily series for many slugs in a single query (avoids the
    N+1 of calling ``history()`` per protocol on every board render)."""
    if not slugs:
        return {}
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = (
        session.query(ProtocolSnapshot.slug, ProtocolSnapshot.date, ProtocolSnapshot.tvl)
        .filter(ProtocolSnapshot.slug.in_(slugs))
        .filter(ProtocolSnapshot.date >= cutoff)
        .order_by(ProtocolSnapshot.slug, ProtocolSnapshot.date)
        .all()
    )
    by_slug: dict[str, list[TvlPoint]] = defaultdict(list)
    for slug, d, tvl in rows:
        by_slug[slug].append(TvlPoint(date=d, tvl=round(tvl or 0.0, 2)))
    return {slug: pts[-days:] for slug, pts in by_slug.items()}


def history(session: Session, slug: str, days: int = 30) -> list[TvlPoint]:
    """Trailing daily TVL series for one protocol (sparklines / trend)."""
    rows = (
        session.query(ProtocolSnapshot)
        .filter(ProtocolSnapshot.slug == slug)
        .order_by(ProtocolSnapshot.date.desc())
        .limit(days)
        .all()
    )
    return [TvlPoint(date=r.date, tvl=round(r.tvl or 0.0, 2)) for r in reversed(rows)]


def aggregate_history(session: Session, days: int = 90) -> list[TvlPoint]:
    """Board-level TVL trend: sum of all tracked protocols per observation
    date, over the trailing window."""
    rows = (
        session.query(
            ProtocolSnapshot.date,
            func.sum(ProtocolSnapshot.tvl).label("total"),
        )
        .group_by(ProtocolSnapshot.date)
        .order_by(ProtocolSnapshot.date.desc())
        .limit(days)
        .all()
    )
    return [TvlPoint(date=d, tvl=round(float(t or 0.0), 2)) for d, t in reversed(rows)]


def aggregate_stats(rows: list[ProtocolSnapshot], alerts: list[Alert]) -> DashboardStats:
    total_tvl = sum(r.tvl for r in rows if r.tvl is not None)
    by_band: dict[str, int] = {}
    for r in rows:
        band = r.risk_band or "unknown"
        by_band[band] = by_band.get(band, 0) + 1

    movers = [r for r in rows if r.change_7d is not None]
    top_gainer = max(movers, key=lambda r: r.change_7d) if movers else None  # type: ignore[arg-type]
    top_loser = min(movers, key=lambda r: r.change_7d) if movers else None  # type: ignore[arg-type]

    return DashboardStats(
        total_tvl=round(total_tvl, 2),
        protocol_count=len(rows),
        by_band=by_band,
        active_critical=sum(1 for a in alerts if a.severity == "critical"),
        active_warning=sum(1 for a in alerts if a.severity == "warning"),
        top_gainer=Mover(slug=top_gainer.slug, name=top_gainer.name or top_gainer.slug,
                         change_7d=round(top_gainer.change_7d, 2)) if top_gainer else None,
        top_loser=Mover(slug=top_loser.slug, name=top_loser.name or top_loser.slug,
                        change_7d=round(top_loser.change_7d, 2)) if top_loser else None,
    )


def _is_stale(rows: list[ProtocolSnapshot]) -> bool:
    if not rows:
        return True
    newest = max((r.captured_at for r in rows if r.captured_at is not None), default=None)
    if newest is None:
        return True
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - newest > STALE_AFTER


def _alerts_from_db(session: Session, limit: int = 50) -> list[Alert]:
    """Recent alerts from the durable log, scoped to the current day so the
    board's "active alerts" means the same thing the /api/alerts page reports
    (which evaluates the live window). Alert ids are deterministic per day,
    so today's rows are exactly the alerts active on the latest data window.
    ``triggered_at`` is an ISO string, so a ``>=`` against the date prefix is a
    valid lexicographic filter."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = (
        session.query(AlertRecord)
        .filter(AlertRecord.triggered_at >= today)
        .order_by(AlertRecord.triggered_at.desc())
        .limit(limit)
        .all()
    )
    return [
        Alert(
            id=r.id, slug=r.slug, protocol=r.protocol, rule=r.rule,
            severity=r.severity, message=r.message, evidence=r.evidence or {},
            triggered_at=r.triggered_at,
        )
        for r in rows
    ]


async def get_dashboard(svc, http, session: Session) -> DashboardResponse:
    """DB-first with live fallback: hydrate via a monitoring pass when empty
    or stale, then assemble the response entirely from the DB."""
    from app.services import alerts as alert_engine

    rows = latest_rows(session)
    if _is_stale(rows):
        # Serialize hydration so a burst of requests on a cold DB runs a single
        # DefiLlama crawl; re-check staleness inside the lock (another request
        # may have just refreshed the board).
        async with _hydration_lock:
            rows = latest_rows(session)
            if _is_stale(rows):
                await alert_engine.run_monitor(svc, http, session)
                rows = latest_rows(session)

    # Single, consistent alert source for both the fresh and hydrated paths.
    alerts = _alerts_from_db(session)

    protocols = [row_to_overview(r) for r in rows]
    series = sparklines(session, [p.slug for p in protocols], SPARKLINE_DAYS)
    for p in protocols:
        p.sparkline = series.get(p.slug, [])
    stats = aggregate_stats(rows, alerts)

    # as_of is the board's freshest observation date (not the top-TVL row's).
    as_of = max((r.date for r in rows), default=None)

    return DashboardResponse(
        stats=stats,
        protocols=protocols,
        alerts=alerts,
        aggregate_history=aggregate_history(session),
        as_of=as_of,
    )
