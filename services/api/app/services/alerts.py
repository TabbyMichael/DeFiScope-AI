"""Automated monitoring rules.

Each rule inspects one ResearchPack and emits zero or more Alerts containing
the triggering evidence (observed value, threshold, metric, window). Rules
are pure functions of pack + settings, which makes them trivially testable
and keeps alert semantics out of the scheduler.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.analysis import metrics
from app.config import get_settings
from app.db import AlertRecord, ProtocolSnapshot
from app.notifiers import Notification, build_notifiers, severity_at_least
from app.schemas import Alert
from app.security.policy import split_visible_alerts
from app.security.principal import Subject
from app.services import onchain
from app.services.protocols import (
    ProtocolResearchService,
    ResearchPack,
    pack_to_overview,
)

logger = logging.getLogger(__name__)


def _alert_id(slug: str, rule: str, day: str) -> str:
    """Deterministic per protocol/rule/day so a re-run does not duplicate alerts."""
    digest = hashlib.sha256(f"{slug}:{rule}:{day}".encode()).hexdigest()[:12]
    return f"alert-{digest}"


def today_alerts(session: Session, limit: int = 50) -> list[Alert]:
    """Today's persisted alerts, read straight from the durable log.

    Alert ids are deterministic per protocol/rule/day, so the current-day rows
    are exactly the alerts active on the latest evaluated window. This lets the
    alerts endpoint serve from the DB instead of running a fresh crawl on every
    request (the scheduler and POST /api/alerts/run own the crawl)."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    rows = (
        session.query(AlertRecord)
        .filter(AlertRecord.triggered_at >= today)
        .order_by(AlertRecord.triggered_at.desc())
        .limit(limit)
        .all()
    )
    return [
        Alert(
            id=r.id,
            slug=r.slug,
            protocol=r.protocol,
            rule=r.rule,
            severity=r.severity,
            message=r.message,
            evidence=r.evidence or {},
            triggered_at=r.triggered_at,
        )
        for r in rows
    ]


def today_alerts_for(
    session: Session,
    subject: Subject,
    *,
    limit: int = 50,
    visible_slugs: set[str] | None = None,
) -> tuple[list[Alert], int]:
    """Today's alerts narrowed to what ``subject`` may read, plus the withheld count.

    A wider pool is read than ``limit`` so the gates cannot shrink the feed:
    withholding removes *content*, and it must never silently drop the rows that
    would otherwise have been visible.
    """
    pool = today_alerts(session, limit=max(limit, 200))
    visible, withheld = split_visible_alerts(pool, subject, visible_slugs=visible_slugs)
    return visible[:limit], withheld


def evaluate_pack(pack: ResearchPack) -> list[Alert]:
    settings = get_settings()
    alerts: list[Alert] = []
    now = datetime.now(UTC)
    name = pack.detail.name
    day = now.strftime("%Y-%m-%d")
    chg_7d = metrics.pct_change(pack.tvl_df, 7)
    chg_1d = metrics.pct_change(pack.tvl_df, 1)

    if chg_7d is not None and chg_7d <= settings.alert_tvl_drop_pct:
        severity = "critical" if chg_7d <= settings.alert_tvl_drop_pct * 2 else "warning"
        alerts.append(
            Alert(
                id=_alert_id(pack.slug, "tvl_drop", day),
                slug=pack.slug,
                protocol=name,
                rule="tvl_drop",
                severity=severity,
                message=f"{name} TVL fell {chg_7d:.1f}% over 7d (threshold {settings.alert_tvl_drop_pct}%).",
                evidence={
                    "metric": "tvl_change_7d_pct",
                    "observed": round(chg_7d, 2),
                    "threshold": settings.alert_tvl_drop_pct,
                    "latest_tvl": pack.latest_tvl,
                    "window_days": 7,
                },
                triggered_at=now.isoformat(),
            )
        )

    if chg_7d is not None and chg_7d >= settings.alert_tvl_surge_pct:
        alerts.append(
            Alert(
                id=_alert_id(pack.slug, "tvl_surge", day),
                slug=pack.slug,
                protocol=name,
                rule="tvl_surge",
                severity="info",
                message=(
                    f"{name} TVL rose {chg_7d:.1f}% over 7d (threshold "
                    f"{settings.alert_tvl_surge_pct}%). Verify whether growth is "
                    "incentive-driven before treating it as adoption."
                ),
                evidence={
                    "metric": "tvl_change_7d_pct",
                    "observed": round(chg_7d, 2),
                    "threshold": settings.alert_tvl_surge_pct,
                    "latest_tvl": pack.latest_tvl,
                    "window_days": 7,
                },
                triggered_at=now.isoformat(),
            )
        )

    inc = metrics.incentive_ratio(pack.detail.tvl_history, pack.detail.staking_history)
    if inc is not None and inc >= settings.alert_staking_ratio:
        alerts.append(
            Alert(
                id=_alert_id(pack.slug, "incentive_dependence", day),
                slug=pack.slug,
                protocol=name,
                rule="incentive_dependence",
                severity="warning",
                message=(
                    f"{name}: staking/incentive TVL is {inc * 100:.0f}% of core TVL - "
                    "heavy dependence on emissions-backed value."
                ),
                evidence={
                    "metric": "staking_to_tvl_ratio",
                    "observed": round(inc, 3),
                    "threshold": settings.alert_staking_ratio,
                },
                triggered_at=now.isoformat(),
            )
        )

    stale = metrics.data_freshness_days(pack.tvl_df)
    if stale is not None and stale > settings.alert_stale_data_days:
        alerts.append(
            Alert(
                id=_alert_id(pack.slug, "stale_data", day),
                slug=pack.slug,
                protocol=name,
                rule="stale_data",
                severity="warning",
                message=(
                    f"{name}: latest DefiLlama observation is {stale}d old - "
                    "downstream metrics may not reflect current conditions."
                ),
                evidence={
                    "metric": "data_age_days",
                    "observed": stale,
                    "threshold": settings.alert_stale_data_days,
                },
                triggered_at=now.isoformat(),
            )
        )

    if chg_1d is not None and chg_1d <= -10:
        alerts.append(
            Alert(
                id=_alert_id(pack.slug, "daily_shock", day),
                slug=pack.slug,
                protocol=name,
                rule="daily_shock",
                severity="critical",
                message=f"{name} TVL dropped {chg_1d:.1f}% in 24h - possible exploit, depeg or mass exit.",
                evidence={
                    "metric": "tvl_change_1d_pct",
                    "observed": round(chg_1d, 2),
                    "threshold": -10.0,
                },
                triggered_at=now.isoformat(),
            )
        )

    # Depeg watch: flag when a stablecoin this protocol mints drifts further
    # from its $1 peg than the configured tolerance within the lookback window.
    # Only runs for issuers in the curated map; a protocol that mints no tracked
    # coin produces no alert here (silence means "not applicable", not "on peg").
    if pack.minted_symbols:
        worst: float | None = None
        worst_coin: str | None = None
        for sym in pack.minted_symbols:
            d = metrics.max_peg_deviation_bps(pack.peg_histories.get(sym, []))
            if d is None:
                continue
            if worst is None or d > worst:
                worst = d
                worst_coin = sym
        if worst is not None and worst >= settings.alert_depeg_bps and worst_coin is not None:
            days = metrics.depeg_duration(
                pack.peg_histories.get(worst_coin, []), settings.alert_depeg_bps
            )
            severity = "critical" if worst >= settings.alert_depeg_bps * 2 else "warning"
            alerts.append(
                Alert(
                    id=_alert_id(pack.slug, "depeg", day),
                    slug=pack.slug,
                    protocol=name,
                    rule="depeg",
                    severity=severity,
                    message=(
                        f"{name}: its stablecoin {worst_coin} traded {worst:.0f} bps "
                        f"off its $1 peg in the last {settings.depeg_window_days}d "
                        f"(threshold {settings.alert_depeg_bps:.0f} bps)."
                    ),
                    evidence={
                        "metric": "max_peg_deviation_bps",
                        "asset": worst_coin,
                        "observed": round(worst, 1),
                        "threshold": settings.alert_depeg_bps,
                        "observations_out_of_band": days,
                        "window_days": settings.depeg_window_days,
                    },
                    triggered_at=now.isoformat(),
                )
            )

    return alerts


def persist_alerts(session: Session, alerts: list[Alert]) -> None:
    """Idempotent upsert: deterministic ids mean a same-day re-run refreshes
    the existing row (latest severity/message/evidence) instead of inserting a
    duplicate. Alert ids encode protocol/rule/day, so the row keeps a stable id
    while its evidence tracks the most recent evaluation of that day."""
    for a in alerts:
        existing = session.get(AlertRecord, a.id)
        if existing is None:
            session.add(
                AlertRecord(
                    id=a.id,
                    slug=a.slug,
                    protocol=a.protocol,
                    rule=a.rule,
                    severity=a.severity,
                    message=a.message,
                    evidence=a.evidence,
                    triggered_at=a.triggered_at,
                )
            )
        else:
            # Same protocol/rule/day re-evaluated: refresh the mutable payload so
            # the durable log reflects the newest observed values.
            existing.severity = a.severity
            existing.message = a.message
            existing.evidence = a.evidence
            existing.triggered_at = a.triggered_at
    session.commit()


def persist_snapshots(session: Session, packs: list[ResearchPack]) -> None:
    """Store one full observation per protocol per day (skip if already
    captured). Writes the complete normalized overview so the dashboard can
    render the board straight from the DB without a live DefiLlama call."""
    for pack in packs:
        date = pack.latest_date
        if date is None:
            continue
        exists = (
            session.query(ProtocolSnapshot)
            .filter(ProtocolSnapshot.slug == pack.slug, ProtocolSnapshot.date == date)
            .first()
        )
        if exists:
            # Data for this (slug, date) is already captured and DefiLlama's
            # daily point is immutable, so don't re-insert. But DO refresh the
            # capture timestamp: the dashboard's staleness check reads
            # max(captured_at), and leaving it frozen would make every request
            # after 6h think the board is stale and re-trigger a live crawl.
            exists.captured_at = datetime.now(UTC)
            continue
        o = pack_to_overview(pack)
        staking_df = metrics.series_to_frame(pack.detail.staking_history)
        staking = float(staking_df["tvl"].iloc[-1]) if not staking_df.empty else None
        session.add(
            ProtocolSnapshot(
                slug=pack.slug,
                date=date,
                name=o.name,
                category=o.category,
                tvl=o.tvl,
                staking_tvl=staking,
                change_7d=o.change_7d,
                change_30d=o.change_30d,
                volatility_30d=o.volatility_30d,
                top_chain=o.top_chain,
                top_chain_share=o.top_chain_share,
                incentive_ratio=o.incentive_ratio,
                stale_days=o.stale_days,
                risk_score=o.risk_score,
                risk_band=o.risk_band,
                captured_at=datetime.now(UTC),
            )
        )
    session.commit()


def backfill_history(session: Session, pack: ResearchPack) -> None:
    """On the first time we see a slug, seed protocol_snapshots with the full
    DefiLlama daily TVL series so history charts and sparklines are populated
    immediately rather than after days of scheduler runs. Derived/risk columns
    are left null for historical rows (only the latest row needs them)."""
    df = pack.tvl_df
    if df is None or df.empty:
        return
    has_rows = session.query(ProtocolSnapshot).filter(ProtocolSnapshot.slug == pack.slug).first()
    if has_rows is not None:
        return
    now = datetime.now(UTC)
    rows = [
        ProtocolSnapshot(
            slug=pack.slug,
            date=str(idx.date()),
            name=pack.detail.name,
            tvl=round(float(val), 2),
            captured_at=now,
        )
        for idx, val in df["tvl"].items()
        if str(idx.date()) != pack.latest_date  # latest handled by persist_snapshots
    ]
    session.add_all(rows)
    session.commit()


async def notify_new_alerts(
    session: Session,
    alerts: list[Alert],
    http,
    settings=None,
) -> int:
    """Fan out *new* alerts to the configured delivery channels.

    Called after ``persist_alerts`` in a monitoring pass. Two guards keep
    delivery honest and non-spammy:

    * **severity gate** - alerts below ``alert_notify_min_severity`` are skipped.
    * **cooldown/dedup** - keyed on the deterministic ``alert-{slug}-{rule}-{day}``
      id via the ``notified_at`` marker, so a 30-min scheduler tick or manual
      re-run never re-sends the same day's alert until the window elapses.

    Delivery is best-effort: a channel raising is logged and swallowed so one
    bad endpoint can't abort the pass or crash the scheduler. The alert is still
    marked notified (it was attempted) once at least one notifier exists.
    Returns the number of alerts dispatched.
    """
    settings = settings or get_settings()
    if not settings.alert_notify_enabled or not alerts:
        return 0

    eligible = [
        a for a in alerts if severity_at_least(a.severity, settings.alert_notify_min_severity)
    ]
    if not eligible:
        return 0

    now = datetime.now(UTC)
    cooldown = timedelta(minutes=settings.alert_notify_cooldown_minutes)
    to_send: list[Alert] = []
    for a in eligible:
        row = session.get(AlertRecord, a.id)
        last = row.notified_at if row is not None else None
        if last is not None:
            if last.tzinfo is None:  # SQLite returns naive timestamps
                last = last.replace(tzinfo=UTC)
            if now - last < cooldown:
                continue
        to_send.append(a)
    if not to_send:
        return 0

    notifiers = build_notifiers(settings)
    if not notifiers:
        return 0  # nothing to deliver to (e.g. webhook-only without a URL)

    notes = [Notification.from_alert(a) for a in to_send]
    for notifier in notifiers:
        for note in notes:
            try:
                await notifier.send(http, note)
            except Exception as exc:  # noqa: BLE001 - one bad channel must not abort the pass
                # Log only the exception TYPE, never str(exc): httpx's
                # raise_for_status() embeds the full request URL, which for
                # Telegram/Slack/Discord/webhook carries the secret token.
                logger.warning(
                    "Notifier %s failed for %s: %s",
                    notifier.name,
                    note.id,
                    type(exc).__name__,
                )

    # Mark dispatched so the next pass honours the cooldown.
    for a in to_send:
        row = session.get(AlertRecord, a.id)
        if row is not None:
            row.notified_at = now
    session.commit()
    return len(to_send)


async def run_monitor(svc: ProtocolResearchService, http, session: Session) -> list[Alert]:
    """Full monitoring pass: fetch the watchlist (curated + top-of-market auto
    discovery), evaluate rules, persist alerts and daily snapshots, then fan
    new alerts out to any configured delivery channels. Called by the scheduler
    and the manual trigger endpoint."""
    slugs = await svc.watchlist_slugs(http)
    # On-chain activity (second provider) is fetched *before* the packs are
    # built, so a pass renders the numbers it just measured rather than the
    # previous pass's. Strictly best-effort: this is the one place Dune is ever
    # called, and a Dune outage must cost the pass its on-chain block, not the
    # whole run. ``refresh`` is a no-op unless a key and a query id exist.
    try:
        await onchain.refresh(session, http, slugs, svc.settings)
    except Exception:  # noqa: BLE001 - second provider must never sink the pass
        logger.exception("On-chain refresh failed; continuing without it")
    # The session is threaded through so the packs built below pick up the rows
    # just written. Alert rules do not read ``pack.onchain``, but the snapshot
    # and RAG steps do, and they must see this pass's measurement.
    packs = await svc.get_packs(slugs, http, session=session)
    alerts: list[Alert] = []
    for pack in packs:
        try:
            alerts.extend(evaluate_pack(pack))
        except Exception as exc:  # noqa: BLE001 - keep monitoring resilient
            logger.warning("Alert evaluation failed for %s: %s", pack.slug, exc)
    persist_alerts(session, alerts)
    await notify_new_alerts(session, alerts, http)
    for pack in packs:
        backfill_history(session, pack)  # seed full history on first sight
    persist_snapshots(session, packs)
    return alerts
