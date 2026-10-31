"""On-chain activity: fetch from Dune, persist, read back for the research pack.

Three responsibilities, deliberately separated:

- ``refresh`` runs saved Dune queries and writes ``onchain_observations``. It is
  called exactly once per monitoring pass ``run_monitor``) and never from a
  request handler, so opening a page cannot spend Dune credits or wait on SQL.
- ``load`` reads the persisted rows only. ``get_pack`` uses this, which is what
  keeps the default dashboard (50+ protocols) free of both an N+1 query and a
  Dune round trip.
- ``OnchainActivity`` is the small value object the pack carries to the
  response layer, mirroring how the DefiLlama summaries are carried.

Status is a first-class output, not an afterthought. ``unconfigured`` and
``no_data`` are different facts about the world and both must be shown as a gap
rather than as zeros:

    unconfigured -> no key / no query id, nothing can be measured
    no_data      -> configured, but no curated mapping or no rows yet
    stale        -> rows exist but the newest one is older than the alert window
    partial      -> the newest day is missing one of the mapped chains
    ok           -> every mapped chain reported for the newest day
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

import httpx
from sqlalchemy.orm import Session

from app.clients.dune import DuneActivityRow, DuneClient
from app.config import Settings, get_settings
from app.db import OnchainObservation
from app.reference_data import load_dune_mapping

logger = logging.getLogger(__name__)

# Closed set of reasons a number may be missing, mirrored by the Literal in
# ``schemas.OnchainActivityOut`` so the generated frontend types are an enum
# instead of a bare string.
OnchainStatus = Literal["ok", "partial", "stale", "no_data", "unconfigured"]

UNCONFIGURED: OnchainStatus = "unconfigured"
NO_DATA: OnchainStatus = "no_data"
STALE: OnchainStatus = "stale"
PARTIAL: OnchainStatus = "partial"
OK: OnchainStatus = "ok"

# Round-robin position for the per-pass budget. Module state rather than DB
# state: it only decides *which* protocols are refreshed next, so losing it on
# restart costs nothing but a restart of the rotation.
_rotation = {"offset": 0}


@dataclass
class OnchainActivity:
    """Aggregated on-chain activity for one protocol on its newest day."""

    status: OnchainStatus
    as_of: str | None = None
    chains: list[str] = field(default_factory=list)
    missing_chains: list[str] = field(default_factory=list)
    active_wallets: int | None = None
    tx_count: int | None = None
    tx_volume_usd: float | None = None
    returning_wallets: int | None = None
    returning_wallet_share: float | None = None
    note: str | None = None


@dataclass
class RefreshReport:
    """What one refresh did - logged by the monitoring pass, asserted by tests."""

    configured: bool = False
    executed: int = 0
    written: int = 0
    skipped_existing: int = 0
    deferred: int = 0
    failed: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.configured:
            return "on-chain refresh skipped (Dune not configured)"
        return (
            f"on-chain refresh: {self.executed} execution(s), {self.written} row(s) written, "
            f"{self.skipped_existing} already present, {self.deferred} deferred, "
            f"{len(self.failed)} failed"
        )


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


async def refresh(
    session: Session,
    http: httpx.AsyncClient,
    slugs: list[str],
    settings: Settings | None = None,
    client: DuneClient | None = None,
) -> RefreshReport:
    """Fetch on-chain activity for up to ``dune_max_protocols_per_pass`` protocols.

    Three guards keep this affordable and non-blocking:

    1. **Unconfigured is a no-op.** No key / no query id means no request at all.
    2. **Today's row short-circuits the execution**, so a re-run (or the 30-min
       scheduler) costs nothing for work already done.
    3. **A per-pass budget with a rotating cursor.** A large watchlist drains
       over several passes instead of one pass growing without bound.

    A single chain failing is recorded and the remaining chains still run: a
    Dune hiccup on one network must not erase the others' numbers.
    """
    settings = settings or get_settings()
    report = RefreshReport(configured=settings.onchain_ready)
    if not report.configured:
        logger.info("On-chain refresh skipped: Dune key or query id missing")
        return report

    mapping = load_dune_mapping()
    candidates = [slug for slug in slugs if mapping.get(slug)]
    if not candidates:
        logger.info("On-chain refresh: no watchlist protocol has a curated contract mapping")
        return report

    budget = max(1, settings.dune_max_protocols_per_pass)
    start = _rotation["offset"] % len(candidates)
    chosen = (candidates[start:] + candidates[:start])[:budget]
    _rotation["offset"] = (start + len(chosen)) % len(candidates)

    client = client or DuneClient()
    today = _today()
    now = datetime.now(UTC)

    for slug in chosen:
        for chain, addresses in mapping[slug].items():
            already = (
                session.query(OnchainObservation)
                .filter_by(slug=slug, chain=chain, date=today)
                .first()
            )
            if already is not None:
                report.skipped_existing += 1
                continue
            try:
                result = await client.run_activity_query(
                    http, chain, addresses, settings.dune_lookback_days
                )
            except Exception as exc:  # noqa: BLE001 - one chain must not sink the pass
                logger.warning("On-chain fetch failed for %s/%s: %s", slug, chain, exc)
                report.failed.append(f"{slug}/{chain}")
                continue
            if result is None:
                # Still executing, or the payload had no rows: defer to next pass.
                report.deferred += 1
                continue
            rows, execution_id = result
            report.executed += 1
            report.written += _store(session, slug, chain, rows, execution_id, now)
        session.commit()

    logger.info(report.summary())
    return report


def _store(
    session: Session,
    slug: str,
    chain: str,
    rows: list[DuneActivityRow],
    execution_id: str,
    fetched_at: datetime,
) -> int:
    """Upsert every returned day. One commit per protocol, by the caller."""
    written = 0
    for row in rows:
        day = row.day.isoformat()
        existing = (
            session.query(OnchainObservation).filter_by(slug=slug, chain=chain, date=day).first()
        )
        if existing is None:
            session.add(
                OnchainObservation(
                    slug=slug,
                    chain=chain,
                    date=day,
                    active_wallets=row.active_wallets,
                    tx_count=row.tx_count,
                    tx_volume_usd=row.tx_volume_usd,
                    returning_wallets=row.returning_wallets,
                    execution_id=execution_id,
                    fetched_at=fetched_at,
                )
            )
        else:
            # Same (slug, chain, day): refresh in place rather than duplicate.
            existing.active_wallets = row.active_wallets
            existing.tx_count = row.tx_count
            existing.tx_volume_usd = row.tx_volume_usd
            existing.returning_wallets = row.returning_wallets
            existing.execution_id = execution_id
            existing.fetched_at = fetched_at
        written += 1
    return written


def _sum_int(values: list[int | None]) -> int | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _sum_float(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present), 2) if present else None


def load(session: Session, slug: str, settings: Settings | None = None) -> OnchainActivity:
    """Read persisted on-chain activity for ``slug``. Never touches the network.

    Aggregates the newest day across every chain that reported, and states the
    reason when the picture is incomplete rather than quietly shrinking the
    total to whatever happened to be available.
    """
    settings = settings or get_settings()
    if not settings.onchain_ready:
        return OnchainActivity(
            status=UNCONFIGURED,
            note=(
                "On-chain metrics need DEFISCOPE_DUNE_API_KEY and "
                "DEFISCOPE_DUNE_ACTIVITY_QUERY_ID; until then there is no measurement, "
                "not a zero."
            ),
        )

    mapping = load_dune_mapping().get(slug, {})
    if not mapping:
        return OnchainActivity(
            status=NO_DATA,
            note="No curated contract mapping for this protocol yet, so nothing is measured.",
        )

    rows = (
        session.query(OnchainObservation)
        .filter(OnchainObservation.slug == slug)
        .order_by(OnchainObservation.date.desc())
        .all()
    )
    if not rows:
        return OnchainActivity(
            status=NO_DATA,
            note="Configured, but no observation has been captured for this protocol yet.",
        )

    latest = rows[0].date
    same_day = [r for r in rows if r.date == latest]
    missing = sorted(set(mapping) - {r.chain for r in same_day})
    chains = sorted({r.chain for r in same_day})

    try:
        age_days = (date.today() - date.fromisoformat(latest)).days
    except ValueError:  # pragma: no cover - stored dates are ISO by construction
        age_days = None

    active = _sum_int([r.active_wallets for r in same_day])
    returning = _sum_int([r.returning_wallets for r in same_day])
    share = None if not active or returning is None else round(returning / active, 4)

    status = OK
    note: str | None = None
    if age_days is not None and age_days > settings.alert_stale_data_days:
        status = STALE
        note = f"Newest on-chain observation is {age_days} days old."
    elif missing:
        status = PARTIAL
        note = f"No on-chain data for {', '.join(missing)} on {latest}."

    return OnchainActivity(
        status=status,
        as_of=latest,
        chains=chains,
        missing_chains=missing,
        active_wallets=active,
        tx_count=_sum_int([r.tx_count for r in same_day]),
        tx_volume_usd=_sum_float([r.tx_volume_usd for r in same_day]),
        returning_wallets=returning,
        returning_wallet_share=share,
        note=note,
    )
