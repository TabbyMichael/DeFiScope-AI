"""Public coverage aggregates: what the service has actually observed.

The landing page and the docs want to state real numbers ("N protocols scored,
M daily observations, K alerts fired this week") instead of adjectives. Those
numbers exist in the store, so they are computed here from it rather than
hard-coded into markup, which would silently rot on the next monitoring pass.

Two rules govern every function in this module:

1. A count is either measured or null. ``None`` means the probe did not answer;
   ``0`` means it answered and there were none. The callers render those
   differently, so they are never collapsed into each other.
2. Nothing here raises. The endpoint backs a *public* page, and a database that
   is briefly unreachable must degrade to an honest "unavailable" panel, not a
   500 on the marketing site. Only the exception *type* is logged, never its
   message, which can carry connection strings.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import AlertRecord, ChatChunk, OnchainObservation, ProtocolSnapshot
from app.schemas import CoverageStatus

logger = logging.getLogger(__name__)

# Alert window for the "recent activity" figure. Seven days is the same horizon
# the TVL-change rules evaluate, so the number on the page means the same thing
# as the alerts it is shown next to.
ALERT_WINDOW_DAYS = 7

# Bands the scorer can emit, fixed here so an empty band renders as 0 rather
# than disappearing from the response and reading as "no data".
BANDS = ("low", "moderate", "elevated", "high", "unknown")


def _iso(dt: datetime | None) -> str | None:
    """Render a stored timestamp as an ISO string, assuming UTC when naive.

    SQLite does not round-trip offsets (the column is declared timezone-aware
    but comes back naive), and this response is published to a public page, so
    the assumption is made explicit rather than left to the reader's locale."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat(timespec="seconds")


def _scalar(session: Session, statement) -> int:
    """Run an aggregate and return its single value, defaulting to 0.

    An empty table makes ``COUNT``/``MAX`` yield NULL, which SQLAlchemy hands
    back as ``None``. For a measured query that is a real zero, not a gap."""
    return session.execute(statement).scalar() or 0


def _latest_per_slug(session: Session):
    """Subquery of each protocol's most recent snapshot row.

    "Latest per slug" is expressed as a ``GROUP BY slug`` subquery joined back
    on ``(slug, date)`` - the unique constraint makes that pair a key, so the
    self-join cannot fan out. Done in SQL rather than in Python because the
    store can hold every protocol in the market, one row per protocol per day.
    """
    latest = (
        select(ProtocolSnapshot.slug.label("slug"), func.max(ProtocolSnapshot.date).label("date"))
        .group_by(ProtocolSnapshot.slug)
        .subquery()
    )
    return (
        select(ProtocolSnapshot)
        .join(
            latest,
            (ProtocolSnapshot.slug == latest.c.slug) & (ProtocolSnapshot.date == latest.c.date),
        )
        .subquery()
    )


def _latest_band_rows(session: Session) -> list[tuple[str | None, int]]:
    """(band, protocol count) for each protocol's most recent snapshot."""
    per_slug = _latest_per_slug(session)
    rows = session.execute(
        select(per_slug.c.risk_band, func.count()).group_by(per_slug.c.risk_band)
    ).all()
    return [(band, int(count)) for band, count in rows]


def _measure(session: Session) -> CoverageStatus:
    """Aggregate the store. Raises on a database error; ``coverage`` converts."""
    settings = get_settings()
    now = datetime.now(UTC)

    snapshots = _scalar(session, select(func.count()).select_from(ProtocolSnapshot))
    tracked = _scalar(
        session,
        select(func.count(func.distinct(ProtocolSnapshot.slug))).select_from(ProtocolSnapshot),
    )
    scored_rows = _scalar(
        session,
        select(func.count())
        .select_from(ProtocolSnapshot)
        .where(ProtocolSnapshot.risk_score.is_not(None)),
    )
    days = _scalar(
        session,
        select(func.count(func.distinct(ProtocolSnapshot.date))).select_from(ProtocolSnapshot),
    )
    categories = _scalar(
        session,
        select(func.count(func.distinct(ProtocolSnapshot.category)))
        .select_from(ProtocolSnapshot)
        .where(ProtocolSnapshot.category.is_not(None)),
    )
    chains = _scalar(
        session,
        select(func.count(func.distinct(ProtocolSnapshot.top_chain)))
        .select_from(ProtocolSnapshot)
        .where(ProtocolSnapshot.top_chain.is_not(None)),
    )
    # Protocols whose newest observation carries a composite score. Distinct
    # slugs, so a protocol with a scored day and a backfilled day counts once.
    per_slug = _latest_per_slug(session)
    scored_protocols = _scalar(
        session,
        select(func.count()).select_from(per_slug).where(per_slug.c.risk_score.is_not(None)),
    )

    band_counts = dict.fromkeys(BANDS, 0)
    for band, count in _latest_band_rows(session):
        band_counts[band if band in band_counts else "unknown"] += count

    cutoff = (now - timedelta(days=ALERT_WINDOW_DAYS)).isoformat(timespec="seconds")
    alerts_total = _scalar(session, select(func.count()).select_from(AlertRecord))
    # triggered_at is stored as a UTC ISO-8601 string. Zero-padded, same-offset
    # timestamps sort lexicographically, so a string comparison is the same
    # filter a date comparison would be - and it matches how ``today_alerts``
    # already reads this column.
    alerts_7d = _scalar(
        session,
        select(func.count())
        .select_from(AlertRecord)
        .where(AlertRecord.triggered_at.is_not(None), AlertRecord.triggered_at >= cutoff),
    )
    severity_rows = session.execute(
        select(AlertRecord.severity, func.count()).group_by(AlertRecord.severity)
    ).all()
    by_severity: dict[str, int] = {"info": 0, "warning": 0, "critical": 0}
    for severity, count in severity_rows:
        by_severity[severity if severity in by_severity else "info"] = int(count)

    onchain_rows = _scalar(session, select(func.count()).select_from(OnchainObservation))
    onchain_protocols = _scalar(
        session,
        select(func.count(func.distinct(OnchainObservation.slug))).select_from(OnchainObservation),
    )
    onchain_chains = _scalar(
        session,
        select(func.count(func.distinct(OnchainObservation.chain))).select_from(OnchainObservation),
    )

    index_chunks = _scalar(session, select(func.count()).select_from(ChatChunk))

    newest_capture = session.execute(select(func.max(ProtocolSnapshot.captured_at))).scalar()

    return CoverageStatus(
        status="ok" if snapshots else "empty",
        as_of=now.isoformat(timespec="seconds"),
        captured_at=_iso(newest_capture),
        protocols_tracked=tracked,
        protocols_scored=scored_protocols,
        observation_days=days,
        categories=categories,
        chains=chains,
        scored_observations=scored_rows,
        bands=band_counts,
        alerts_total=alerts_total,
        alerts_7d=alerts_7d,
        alerts_by_severity=by_severity,
        onchain_observations=onchain_rows,
        onchain_protocols=onchain_protocols,
        onchain_chains=onchain_chains,
        index_chunks=index_chunks,
        llm_configured=bool(settings.openai_api_key),
        onchain_configured=settings.onchain_ready,
        monitor_interval_minutes=settings.monitor_interval_minutes,
        protocols_curated=len(settings.protocol_slugs),
    )


def coverage(session: Session) -> CoverageStatus:
    """Aggregate coverage for public display; never raises.

    On a database error the counts come back ``None`` with
    ``status="unavailable"`` rather than 0, so a consumer can tell "nothing has
    been observed" from "we could not look". Configuration-derived fields still
    resolve, because they do not depend on the store."""
    try:
        return _measure(session)
    except SQLAlchemyError as exc:
        logger.warning("Coverage aggregates unavailable: %s", type(exc).__name__)
        settings = get_settings()
        return CoverageStatus(
            status="unavailable",
            llm_configured=bool(settings.openai_api_key),
            onchain_configured=settings.onchain_ready,
            monitor_interval_minutes=settings.monitor_interval_minutes,
            protocols_curated=len(settings.protocol_slugs),
        )
