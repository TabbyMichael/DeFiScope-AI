"""DB-first dashboard reads.

The board renders from `protocol_snapshots` / `alert_records`. Only when the
DB is empty or its newest capture is stale do we run a live monitoring pass
(which also backfills history), so normal dashboard loads never hit
DefiLlama directly.

Reads are scope-aware: an analyst restricted to two categories sees *their*
board, and every aggregate below is computed over the visible rows only. A
scoped user reading a "total TVL" summed across protocols they cannot open
would be a correctness bug, not a cosmetic one.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.db import ProtocolSnapshot
from app.schemas import (
    Alert,
    DashboardResponse,
    DashboardStats,
    Mover,
    ProtocolOverview,
    RiskPoint,
    TvlPoint,
)
from app.security.principal import ANONYMOUS, Scope, Subject

# If the newest capture is older than this, treat the board as stale and run a
# live hydration pass. The scheduler captures every few minutes, so this only
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


def _scope_rows(rows: list[ProtocolSnapshot], scope: Scope | None) -> list[ProtocolSnapshot]:
    """Drop rows outside the subject's data scope.

    Filtered in Python rather than SQL on purpose: ``Scope.allows`` denies an
    *unknown* attribute (a row with no category) when a restriction is
    configured, and it is the exact predicate the detail endpoints use - so a
    row can never be listed but un-openable, or vice versa.
    """
    if scope is None or not scope.restricted:
        return rows
    return [r for r in rows if scope.allows(r.category, r.top_chain)]


def latest_rows(session: Session, scope: Scope | None = None) -> list[ProtocolSnapshot]:
    """Newest *monitored* snapshot per slug via a max(date) group-by joined back.

    Board-integrity guard: catalog pre-seed rows (``monitored = 0``) persist
    detail-page data for protocols the watchlist deliberately does not track
    (CEX/Bridge/Chain totals). They must not enter board totals, band counts or
    movers, so they are excluded here - the single latest-row source every
    board read funnels through. ``coalesce`` keeps legacy NULL rows (written
    before the column existed) in the board, matching the backfill semantics.

    The join can theoretically return more than one row per slug if duplicate
    (slug, date) rows exist (e.g. from a pre-unique-constraint database or a
    concurrent write), so we keep exactly one per slug here as a safety net."""
    sub = (
        session.query(
            ProtocolSnapshot.slug,
            func.max(ProtocolSnapshot.date).label("max_date"),
        )
        .filter(func.coalesce(ProtocolSnapshot.monitored, 1) != 0)
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
        .filter(func.coalesce(ProtocolSnapshot.monitored, 1) != 0)
        .order_by(ProtocolSnapshot.tvl.desc())
        .all()
    )
    by_slug: dict[str, ProtocolSnapshot] = {}
    for r in rows:
        if r.slug not in by_slug:
            by_slug[r.slug] = r
    return _scope_rows(list(by_slug.values()), scope)


def _latest_monitored_subquery(session: Session):
    """The max(date) group-by-per-slug subquery every board read funnels
    through. Pre-seed rows (``monitored = 0``) are excluded here - the single
    board-integrity guard - and ``coalesce`` keeps legacy NULL rows in the board."""
    return (
        session.query(
            ProtocolSnapshot.slug,
            func.max(ProtocolSnapshot.date).label("max_date"),
        )
        .filter(func.coalesce(ProtocolSnapshot.monitored, 1) != 0)
        .group_by(ProtocolSnapshot.slug)
        .subquery()
    )


def _escape_like(term: str) -> str:
    """Neutralize LIKE wildcards so a search term is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_scope_sql(query, scope: Scope | None):
    """Narrow a ProtocolSnapshot query to the subject's data scope in SQL.

    Mirrors ``_scope_rows``' deny-unknown rule: a category/chain restriction
    uses ``IN``, which drops NULL-attribute rows - exactly what ``Scope.allows``
    does in Python - so a paginated read cannot leak a row the board would hide.
    Applying it in SQL (not post-fetch) is what lets ``total`` and the page
    window reflect only what the caller may see over the full ~5000-row board."""
    if scope is None or not scope.restricted:
        return query
    if scope.categories is not None:
        query = query.filter(ProtocolSnapshot.category.in_(tuple(scope.categories)))
    if scope.chains is not None:
        query = query.filter(ProtocolSnapshot.top_chain.in_(tuple(scope.chains)))
    return query


# Board sort allowlist: watchlist key -> the snapshot column to order by. The
# router constrains ``sort`` to this set via an enum, so a caller string never
# reaches SQL as text - it is only ever a lookup into one of these columns.
BOARD_SORT_COLUMNS: dict[str, object] = {
    "risk": ProtocolSnapshot.risk_score,
    "tvl": ProtocolSnapshot.tvl,
    "7d": ProtocolSnapshot.change_7d,
    "30d": ProtocolSnapshot.change_30d,
}


def latest_rows_paginated(
    session: Session,
    *,
    sort: str = "risk",
    direction: str = "desc",
    band: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 100,
    scope: Scope | None = None,
) -> tuple[list[ProtocolSnapshot], int]:
    """One page of the board's latest monitored rows, plus the filtered total.

    Everything - band filter, name/slug search, scope, ordering and paging -
    happens in SQL, so a 5000-protocol watchlist never serializes the whole set
    to the browser or loads 5000 ORM objects to slice one page client-side. The
    ``uq_snapshot_slug_date`` constraint guarantees one row per (slug, date), so
    the join on (slug, max_date) yields exactly one row per slug - no post-fetch
    de-dup is needed (unlike the whole-board ``latest_rows`` safety net)."""
    sub = _latest_monitored_subquery(session)
    query = (
        session.query(ProtocolSnapshot)
        .join(
            sub,
            and_(
                ProtocolSnapshot.slug == sub.c.slug,
                ProtocolSnapshot.date == sub.c.max_date,
            ),
        )
        .filter(func.coalesce(ProtocolSnapshot.monitored, 1) != 0)
    )
    query = _apply_scope_sql(query, scope)

    if band:
        if band == "unknown":
            query = query.filter(
                or_(
                    ProtocolSnapshot.risk_band.is_(None),
                    ProtocolSnapshot.risk_band == "unknown",
                )
            )
        else:
            query = query.filter(ProtocolSnapshot.risk_band == band)

    term = (q or "").strip()
    if term:
        like = f"%{_escape_like(term)}%"
        query = query.filter(
            or_(
                ProtocolSnapshot.name.ilike(like, escape="\\"),
                ProtocolSnapshot.slug.ilike(like, escape="\\"),
            )
        )

    total = query.count()
    column = BOARD_SORT_COLUMNS.get(sort, ProtocolSnapshot.risk_score)
    # Nulls always sort to the far end so "riskiest first" / "biggest TVL" never
    # bury the scored rows under the unscored tail, whichever direction asked.
    order_terms = [
        column.is_(None).asc(),
        column.desc() if direction == "desc" else column.asc(),
        ProtocolSnapshot.slug.asc(),  # stable tiebreak for equal values
    ]
    rows = query.order_by(*order_terms).offset(max(0, offset)).limit(max(0, limit)).all()
    return rows, total


def board_summary(
    session: Session, *, scope: Scope | None = None, alerts: list[Alert] | None = None
) -> tuple[DashboardStats, str | None]:
    """Aggregate the *whole* scoped board in one lightweight column scan.

    The watchlist page shows market-wide totals (protocol count, total TVL, band
    tiles, top movers, as-of) that must span every monitored protocol - not just
    the current page or the active band/search filter, which is what
    ``latest_rows_paginated`` returns. Reading bare columns (not ORM entities)
    keeps a 5000-row scan cheap. ``alerts`` only feeds the two active-alert
    counters; pass ``None`` when the caller adds them separately."""
    sub = _latest_monitored_subquery(session)
    query = (
        session.query(
            ProtocolSnapshot.slug,
            ProtocolSnapshot.risk_band,
            ProtocolSnapshot.tvl,
            ProtocolSnapshot.change_7d,
            ProtocolSnapshot.name,
            ProtocolSnapshot.date,
        )
        .join(
            sub,
            and_(
                ProtocolSnapshot.slug == sub.c.slug,
                ProtocolSnapshot.date == sub.c.max_date,
            ),
        )
        .filter(func.coalesce(ProtocolSnapshot.monitored, 1) != 0)
    )
    query = _apply_scope_sql(query, scope)

    total_tvl = 0.0
    count = 0
    by_band: dict[str, int] = {}
    as_of: str | None = None
    gainer: tuple[str, str, float] | None = None
    loser: tuple[str, str, float] | None = None
    for slug, band, tvl, chg_7d, name, d in query.all():
        count += 1
        if tvl is not None:
            total_tvl += tvl
        key = band or "unknown"
        by_band[key] = by_band.get(key, 0) + 1
        if d is not None and (as_of is None or d > as_of):
            as_of = d
        if chg_7d is not None:
            label = name or slug
            if gainer is None or chg_7d > gainer[2]:
                gainer = (slug, label, chg_7d)
            if loser is None or chg_7d < loser[2]:
                loser = (slug, label, chg_7d)

    alerts = alerts or []
    stats = DashboardStats(
        total_tvl=round(total_tvl, 2),
        protocol_count=count,
        by_band=by_band,
        active_critical=sum(1 for a in alerts if a.severity == "critical"),
        active_warning=sum(1 for a in alerts if a.severity == "warning"),
        top_gainer=Mover(slug=gainer[0], name=gainer[1], change_7d=round(gainer[2], 2))
        if gainer
        else None,
        top_loser=Mover(slug=loser[0], name=loser[1], change_7d=round(loser[2], 2))
        if loser
        else None,
    )
    return stats, as_of


def latest_row_for(session: Session, slug: str) -> ProtocolSnapshot | None:
    """Newest snapshot for one slug - the attribute bag a scope check needs."""
    return (
        session.query(ProtocolSnapshot)
        .filter(ProtocolSnapshot.slug == slug)
        .order_by(ProtocolSnapshot.date.desc())
        .first()
    )


def freshness_hours(session: Session) -> float | None:
    """Hours since the newest *monitored* capture, or None when nothing is
    stored yet. Pre-seed rows are captured continuously by the seed loop, so
    counting them here would keep a stale board forever looking fresh and
    suppress the dashboard's own hydration pass.

    Kept here (next to ``STALE_AFTER``) so the manual-run policy and the
    dashboard's own staleness check cannot drift apart."""
    newest = (
        session.query(func.max(ProtocolSnapshot.captured_at))
        .filter(func.coalesce(ProtocolSnapshot.monitored, 1) != 0)
        .scalar()
    )
    if newest is None:
        return None
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - newest).total_seconds() / 3600)


def visible_slugs(session: Session, subject: Subject) -> set[str] | None:
    """The slugs this subject may see, or None when unrestricted.

    The single source of truth for "what is in scope" outside the board itself:
    alert feeds, chat citations and per-slug detail checks all narrow to this
    set, so they cannot disagree about whether a protocol is visible."""
    if not subject.scope.restricted:
        return None
    return {r.slug for r in latest_rows(session, subject.scope)}


def sparklines(
    session: Session, slugs: list[str], days: int = SPARKLINE_DAYS
) -> dict[str, list[TvlPoint]]:
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


def risk_history(session: Session, slug: str, days: int = 90) -> list[RiskPoint]:
    """Trailing daily risk-score observations for one protocol.

    Filters to rows that actually carry a ``risk_score``: the initial DefiLlama
    backfill seeds historical TVL days without re-scoring them (score is null),
    so including those would plot a misleading flat/zero baseline. The result is
    the genuine trend of the composite score over the days the scheduler ran.
    Ascending by date."""
    rows = (
        session.query(ProtocolSnapshot)
        .filter(ProtocolSnapshot.slug == slug)
        .filter(ProtocolSnapshot.risk_score.isnot(None))
        .order_by(ProtocolSnapshot.date.desc())
        .limit(days)
        .all()
    )
    return [RiskPoint(date=r.date, score=r.risk_score, band=r.risk_band) for r in reversed(rows)]


def aggregate_history(
    session: Session, days: int = 90, slugs: list[str] | None = None
) -> list[TvlPoint]:
    """Board-level TVL trend: sum of all *visible* protocols per observation
    date, over the trailing window.

    ``slugs`` is the caller's visible set. Passing an empty list is not the same
    as None: a scoped subject who can see nothing gets an empty series rather
    than the whole market's total."""
    if slugs is not None and not slugs:
        return []
    query = session.query(
        ProtocolSnapshot.date,
        func.sum(ProtocolSnapshot.tvl).label("total"),
    ).filter(func.coalesce(ProtocolSnapshot.monitored, 1) != 0)
    if slugs is not None:
        query = query.filter(ProtocolSnapshot.slug.in_(slugs))
    # Unrestricted board: exclude unmonitored pre-seed rows by slug, since the
    # seed loop can persist protocols (CEX totals) the watchlist excludes.
    if slugs is None:
        monitored_sub = (
            session.query(ProtocolSnapshot.slug)
            .filter(func.coalesce(ProtocolSnapshot.monitored, 1) != 0)
            .distinct()
            .scalar_subquery()
        )
        query = query.filter(ProtocolSnapshot.slug.in_(monitored_sub))
    rows = (
        query.group_by(ProtocolSnapshot.date)
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
        top_gainer=Mover(
            slug=top_gainer.slug,
            name=top_gainer.name or top_gainer.slug,
            change_7d=round(top_gainer.change_7d, 2),
        )
        if top_gainer
        else None,
        top_loser=Mover(
            slug=top_loser.slug,
            name=top_loser.name or top_loser.slug,
            change_7d=round(top_loser.change_7d, 2),
        )
        if top_loser
        else None,
    )


def _is_stale(rows: list[ProtocolSnapshot]) -> bool:
    if not rows:
        return True
    newest = max((r.captured_at for r in rows if r.captured_at is not None), default=None)
    if newest is None:
        return True
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=UTC)
    return datetime.now(UTC) - newest > STALE_AFTER


async def get_dashboard(
    svc, http, session: Session, subject: Subject | None = None
) -> DashboardResponse:
    """DB-first with live fallback: hydrate via a monitoring pass when empty
    or stale, then assemble the response entirely from the DB.

    Freshness is judged on the *whole* dataset, not the caller's slice: a scope
    that happens to match no rows must not re-trigger a full crawl on every
    page load. Presentation is then narrowed to the subject's scope."""
    from app.services import alerts as alert_engine

    subject = subject or ANONYMOUS
    all_rows = latest_rows(session)
    if _is_stale(all_rows):
        # Serialize hydration so a burst of requests on a cold DB runs a single
        # DefiLlama crawl; re-check staleness inside the lock (another request
        # may have just refreshed the board).
        async with _hydration_lock:
            all_rows = latest_rows(session)
            if _is_stale(all_rows):
                await alert_engine.run_monitor(svc, http, session)
                all_rows = latest_rows(session)

    rows = _scope_rows(all_rows, subject.scope)
    visible_slugs = sorted(r.slug for r in rows) if subject.scope.restricted else None

    # Single, consistent alert source for both the fresh and hydrated paths.
    # Read today's persisted alerts from the shared helper (no crawl here), then
    # apply the scope + severity gates: content may be withheld, the count is not.
    alerts, withheld = alert_engine.today_alerts_for(session, subject, visible_slugs=visible_slugs)

    protocols = [row_to_overview(r) for r in rows]
    # The Overview embeds a *compact* board preview, not the whole market: the
    # aggregate stats above span every monitored row, but the inline protocol
    # list is capped (rows arrive ordered by TVL, so the biggest names lead) and
    # sparklines are fetched only for that preview. The full market is paged via
    # GET /api/watchlist, so the landing payload stays small at 5000 protocols.
    from app.config import get_settings

    preview_size = max(0, get_settings().board_preview_size)
    protocols = protocols[:preview_size]
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
        aggregate_history=aggregate_history(session, slugs=visible_slugs),
        as_of=as_of,
        withheld_alerts=withheld,
    )
