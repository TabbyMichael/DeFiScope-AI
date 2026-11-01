"""DB-first protocol detail assembly.

The research payload a protocol page renders used to be rebuilt on every request
by crawling DefiLlama (``protocols.get_pack``): a cold slug cost ~13 s and even a
warm one re-derived the whole pack in-process, evaporating on restart. This
module answers the *identical* ``ProtocolResearch`` contract entirely from the
database - the same source-of-truth model the dashboard already reads from - so
opening a page is an indexed row read, never a network call.

Two honest states, both served instantly:

* **Seeded** (a monitoring or pre-seed pass captured a snapshot): the full
  payload - overview, TVL series, chain breakdown, explainable-risk JSON,
  on-chain activity.
* **Listed but not yet captured**: catalog metadata only (name/category/TVL/
  headline changes), every analysis field ``None`` and the band ``unknown``.
  A gap, never a zero, and never a crawl - the Explorer already links to this
  shape today.

A slug with *neither* a catalog row nor a snapshot raises :class:`ProtocolUnknown`,
which the router maps to 404 - so "unknown protocol" stays distinguishable from
"known protocol, no data yet".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.analysis import metrics
from app.config import Settings
from app.db import ProtocolCatalog, ProtocolSnapshot
from app.schemas import (
    ChainShare,
    OnchainActivityOut,
    ProtocolOverview,
    ProtocolResearch,
    RiskAssessmentOut,
    TvlPoint,
)
from app.services import onchain as onchain_service
from app.services.dashboard import _snapshot_age_days

# Trailing TVL window the detail page charts, matching the pack path's default.
DEFAULT_WINDOW_DAYS = 180


class ProtocolUnknown(Exception):
    """No catalog row and no snapshot for the slug.

    Raised only when the protocol is genuinely absent from the discovery catalog,
    so it never masks a merely-uncrawled slug (those load with gap fields)."""


@dataclass
class DetailPack:
    """Everything the read models (research payload, brief) need, DB-sourced."""

    slug: str
    name: str
    category: str | None
    url: str | None
    overview: ProtocolOverview
    tvl_series: list[TvlPoint] = field(default_factory=list)
    chains: list[ChainShare] = field(default_factory=list)
    # ``risk_json`` verbatim (indicators + data_gaps), or None when the slug was
    # never scored. Kept as a dict so briefs can read indicators without the
    # research response re-validating them.
    risk: dict | None = None
    onchain: OnchainActivityOut | None = None

    @property
    def data_gaps(self) -> list[str]:
        return list((self.risk or {}).get("data_gaps") or [])


def _latest_snapshot(session: Session, slug: str) -> ProtocolSnapshot | None:
    return (
        session.query(ProtocolSnapshot)
        .filter(ProtocolSnapshot.slug == slug)
        .order_by(ProtocolSnapshot.date.desc())
        .first()
    )


def _overview_from_row(row: ProtocolSnapshot) -> ProtocolOverview:
    stale_days = max(row.stale_days or 0, _snapshot_age_days(row.date))
    return ProtocolOverview(
        slug=row.slug,
        name=row.name or row.slug,
        category=row.category,
        tvl=row.tvl,
        change_7d=row.change_7d,
        change_30d=row.change_30d,
        volatility_30d=row.volatility_30d,
        top_chain=row.top_chain,
        top_chain_share=row.top_chain_share,
        incentive_ratio=row.incentive_ratio,
        fees_1d=row.fees_1d,
        fees_30d=row.fees_30d,
        revenue_1d=row.revenue_1d,
        volume_1d=row.volume_1d,
        fees_tvl=row.fees_tvl,
        volume_tvl=row.volume_tvl,
        depeg_worst_bps=row.depeg_worst_bps,
        depeg_asset=row.depeg_asset,
        risk_score=row.risk_score,
        risk_band=row.risk_band or "unknown",
        stale_days=stale_days,
        source="db",
        as_of=row.date,
    )


def _overview_from_catalog(cat: ProtocolCatalog) -> ProtocolOverview:
    """Gap-only overview for a listed protocol with no captured snapshot.

    Carries the discovery metadata the Explorer already shows (headline TVL and
    the directory's 7d change) and nothing the analysis pass owns; every derived
    field stays ``None`` and the band ``unknown``."""
    return ProtocolOverview(
        slug=cat.slug,
        name=cat.name or cat.slug,
        category=cat.category,
        tvl=cat.tvl,
        change_7d=cat.change_7d,
        risk_score=cat.risk_score,
        risk_band=cat.risk_band or "unknown",
        source="catalog",
        as_of=None,
    )


def _tvl_series(session: Session, slug: str, window_days: int) -> list[TvlPoint]:
    rows = (
        session.query(ProtocolSnapshot.date, ProtocolSnapshot.tvl)
        .filter(ProtocolSnapshot.slug == slug, ProtocolSnapshot.tvl.isnot(None))
        .order_by(ProtocolSnapshot.date.desc())
        .limit(window_days)
        .all()
    )
    return [TvlPoint(date=d, tvl=round(float(t or 0.0), 2)) for d, t in reversed(rows)]


def _chains(row: ProtocolSnapshot) -> list[ChainShare]:
    chain_tvls = row.chain_shares or {}
    if not chain_tvls:
        return []
    info = metrics.chain_concentration({c: float(v) for c, v in chain_tvls.items()})
    return [
        ChainShare(
            chain=chain,
            tvl=round(float(chain_tvls[chain]), 2),
            share=round(share, 4),
        )
        for chain, share in sorted(info.get("shares", {}).items(), key=lambda kv: -kv[1])
    ]


def load_detail(
    session: Session,
    slug: str,
    settings: Settings | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> DetailPack:
    """Assemble the protocol's read model entirely from the DB.

    Reads: latest snapshot (analysis + headline), the trailing TVL series, the
    catalog row (for the home URL and the not-yet-seeded case) and on-chain
    activity (itself a DB read, never a Dune call). No network I/O.
    """
    row = _latest_snapshot(session, slug)
    cat = session.get(ProtocolCatalog, slug)
    if row is None and cat is None:
        raise ProtocolUnknown(slug)

    overview = _overview_from_row(row) if row is not None else _overview_from_catalog(cat)
    name = overview.name
    # A snapshot row carries no home URL; the catalog does. Prefer the catalog's,
    # fall back to the row's name-only context.
    url = cat.url if cat is not None else None
    risk = row.risk_json if row is not None else None

    pack = DetailPack(
        slug=slug,
        name=name,
        category=overview.category,
        url=url,
        overview=overview,
        tvl_series=_tvl_series(session, slug, window_days),
        chains=_chains(row) if row is not None else [],
        risk=risk,
    )
    # On-chain activity is keyed off the DB, so it is loaded for both the seeded
    # and gap-only cases; the block reports its own status (ok/partial/no_data/
    # unconfigured) rather than being silently dropped.
    pack.onchain = _onchain_out(onchain_service.load(session, slug, settings))
    return pack


def _onchain_out(activity: onchain_service.OnchainActivity | None) -> OnchainActivityOut:
    """Map the on-chain value object onto the response contract.

    Mirrors ``protocols._onchain_out``: a non-``OnchainActivity`` (no session /
    not loaded) is an explicit ``unconfigured`` gap, never zero activity."""
    if not isinstance(activity, onchain_service.OnchainActivity):
        return OnchainActivityOut(
            status="unconfigured",
            note="On-chain metrics were not loaded for this request.",
        )
    return OnchainActivityOut(
        status=activity.status,
        as_of=activity.as_of,
        chains=activity.chains,
        missing_chains=activity.missing_chains,
        active_wallets=activity.active_wallets,
        tx_count=activity.tx_count,
        tx_volume_usd=activity.tx_volume_usd,
        returning_wallets=activity.returning_wallets,
        returning_wallet_share=activity.returning_wallet_share,
        note=activity.note,
    )


def to_research(pack: DetailPack) -> ProtocolResearch:
    """Build the ``ProtocolResearch`` response from a DB-loaded pack.

    The response contract is identical to the old pack path, so the frontend's
    generated types and every consumer stay unchanged. ``sources`` keeps naming
    the upstream (DefiLlama) even though this render is DB-sourced, because the
    numbers still *originate* there - provenance is about the data, not the hop."""
    risk_out = RiskAssessmentOut.model_validate(pack.risk) if pack.risk else RiskAssessmentOut()
    onchain = pack.onchain or OnchainActivityOut(
        status="unconfigured",
        note="On-chain metrics were not loaded for this request.",
    )
    return ProtocolResearch(
        slug=pack.slug,
        name=pack.name,
        category=pack.category,
        url=pack.url,
        overview=pack.overview,
        tvl_series=pack.tvl_series,
        chains=pack.chains,
        risk=risk_out,
        onchain=onchain,
        data_gaps=pack.data_gaps,
        as_of=pack.overview.as_of or "n/a",
        sources=[
            f"https://defillama.com/protocol/{pack.slug}",
            "https://api.llama.fi",
        ],
    )


def latest_observation_date(session: Session, slug: str) -> date | None:
    """The newest snapshot's observation date, or None when never captured. Kept
    for the manual-run policy's per-slug freshness hint; parses the ISO string
    stored on the row."""
    row = _latest_snapshot(session, slug)
    if row is None or not row.date:
        return None
    try:
        return date.fromisoformat(row.date)
    except ValueError:
        return None
