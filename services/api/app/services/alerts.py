"""Automated monitoring rules.

Each rule inspects one ResearchPack and emits zero or more Alerts containing
the triggering evidence (observed value, threshold, metric, window). Rules
are pure functions of pack + settings, which makes them trivially testable
and keeps alert semantics out of the scheduler.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.analysis import metrics
from app.config import get_settings
from app.db import AlertRecord, ProtocolSnapshot
from app.schemas import Alert
from app.services.protocols import ProtocolResearchService, ResearchPack

logger = logging.getLogger(__name__)


def _alert_id(slug: str, rule: str, day: str) -> str:
    """Deterministic per protocol/rule/day so a re-run does not duplicate alerts."""
    digest = hashlib.sha256(f"{slug}:{rule}:{day}".encode()).hexdigest()[:12]
    return f"alert-{digest}"


def evaluate_pack(pack: ResearchPack) -> list[Alert]:
    settings = get_settings()
    alerts: list[Alert] = []
    now = datetime.now(timezone.utc)
    name = pack.detail.name
    day = now.strftime("%Y-%m-%d")
    chg_7d = metrics.pct_change(pack.tvl_df, 7)
    chg_1d = metrics.pct_change(pack.tvl_df, 1)

    if chg_7d is not None and chg_7d <= settings.alert_tvl_drop_pct:
        severity = "critical" if chg_7d <= settings.alert_tvl_drop_pct * 2 else "warning"
        alerts.append(Alert(
            id=_alert_id(pack.slug, "tvl_drop", day), slug=pack.slug, protocol=name,
            rule="tvl_drop", severity=severity,
            message=f"{name} TVL fell {chg_7d:.1f}% over 7d (threshold {settings.alert_tvl_drop_pct}%).",
            evidence={"metric": "tvl_change_7d_pct", "observed": round(chg_7d, 2),
                      "threshold": settings.alert_tvl_drop_pct,
                      "latest_tvl": pack.latest_tvl, "window_days": 7},
            triggered_at=now.isoformat(),
        ))

    if chg_7d is not None and chg_7d >= settings.alert_tvl_surge_pct:
        alerts.append(Alert(
            id=_alert_id(pack.slug, "tvl_surge", day), slug=pack.slug, protocol=name,
            rule="tvl_surge", severity="info",
            message=(f"{name} TVL rose {chg_7d:.1f}% over 7d (threshold "
                     f"{settings.alert_tvl_surge_pct}%). Verify whether growth is "
                     "incentive-driven before treating it as adoption."),
            evidence={"metric": "tvl_change_7d_pct", "observed": round(chg_7d, 2),
                      "threshold": settings.alert_tvl_surge_pct,
                      "latest_tvl": pack.latest_tvl, "window_days": 7},
            triggered_at=now.isoformat(),
        ))

    inc = metrics.incentive_ratio(pack.detail.tvl_history, pack.detail.staking_history)
    if inc is not None and inc >= settings.alert_staking_ratio:
        alerts.append(Alert(
            id=_alert_id(pack.slug, "incentive_dependence", day), slug=pack.slug, protocol=name,
            rule="incentive_dependence", severity="warning",
            message=(f"{name}: staking/incentive TVL is {inc * 100:.0f}% of core TVL - "
                     "heavy dependence on emissions-backed value."),
            evidence={"metric": "staking_to_tvl_ratio", "observed": round(inc, 3),
                      "threshold": settings.alert_staking_ratio},
            triggered_at=now.isoformat(),
        ))

    stale = metrics.data_freshness_days(pack.tvl_df)
    if stale is not None and stale > settings.alert_stale_data_days:
        alerts.append(Alert(
            id=_alert_id(pack.slug, "stale_data", day), slug=pack.slug, protocol=name,
            rule="stale_data", severity="warning",
            message=(f"{name}: latest DefiLlama observation is {stale}d old - "
                     "downstream metrics may not reflect current conditions."),
            evidence={"metric": "data_age_days", "observed": stale,
                      "threshold": settings.alert_stale_data_days},
            triggered_at=now.isoformat(),
        ))

    if chg_1d is not None and chg_1d <= -10:
        alerts.append(Alert(
            id=_alert_id(pack.slug, "daily_shock", day), slug=pack.slug, protocol=name,
            rule="daily_shock", severity="critical",
            message=f"{name} TVL dropped {chg_1d:.1f}% in 24h - possible exploit, depeg or mass exit.",
            evidence={"metric": "tvl_change_1d_pct", "observed": round(chg_1d, 2),
                      "threshold": -10.0},
            triggered_at=now.isoformat(),
        ))

    return alerts


def persist_alerts(session: Session, alerts: list[Alert]) -> None:
    """Idempotent upsert: deterministic ids mean a same-day re-run updates
    evidence instead of inserting duplicates."""
    for a in alerts:
        if session.get(AlertRecord, a.id) is None:
            session.add(AlertRecord(
                id=a.id, slug=a.slug, protocol=a.protocol, rule=a.rule,
                severity=a.severity, message=a.message, evidence=a.evidence,
                triggered_at=a.triggered_at,
            ))
    session.commit()


def persist_snapshots(session: Session, packs: list[ResearchPack]) -> None:
    """Store one observation per protocol per day (skip if already captured)."""
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
            continue
        staking_df = metrics.series_to_frame(pack.detail.staking_history)
        staking = float(staking_df["tvl"].iloc[-1]) if not staking_df.empty else None
        session.add(ProtocolSnapshot(
            slug=pack.slug, date=date, tvl=pack.latest_tvl, staking_tvl=staking,
            risk_score=pack.risk.composite_score if pack.risk else None,
            risk_band=pack.risk.band if pack.risk else None,
            captured_at=datetime.now(timezone.utc),
        ))
    session.commit()


async def run_monitor(svc: ProtocolResearchService, http, session: Session) -> list[Alert]:
    """Full monitoring pass: fetch configured protocols, evaluate rules,
    persist alerts and daily snapshots. Called by the scheduler and the
    manual trigger endpoint."""
    settings = get_settings()
    packs = await svc.get_packs(settings.protocol_slugs, http)
    alerts: list[Alert] = []
    for pack in packs:
        try:
            alerts.extend(evaluate_pack(pack))
        except Exception as exc:  # noqa: BLE001 - keep monitoring resilient
            logger.warning("Alert evaluation failed for %s: %s", pack.slug, exc)
    persist_alerts(session, alerts)
    persist_snapshots(session, packs)
    return alerts
