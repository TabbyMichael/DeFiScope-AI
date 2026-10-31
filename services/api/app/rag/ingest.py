"""Build and persist the chat's evidence index (roadmap #8).

Two source families are indexed into ``chat_chunks``:
- the repo ``docs/`` markdown (methodology, architecture, DeFi primer, sample
  brief) - these answer "how do you score?" / "what is a depeg?" questions;
- each monitored protocol's live evidence (indicators with their evidence AND
  limitation text, data gaps, headline numbers, recent alerts) - these answer
  "why is Aave flagged?" questions and are what the guardrail quotes verbatim.

Ingestion is idempotent (content-hash chunk ids reuse existing embeddings) and
runs as a non-blocking background task at startup, mirroring the warm-up pass:
readiness never waits on embedding latency, and a failure degrades to a smaller
index rather than crashing the app.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import AlertRecord, ChatChunk, ProtocolSnapshot
from app.rag.chunking import Chunk, chunk_evidence, chunk_markdown
from app.rag.embeddings import embed_texts
from app.services.protocols import ProtocolResearchService, ResearchPack, pack_to_overview

logger = logging.getLogger(__name__)

# (doc_id, human source name, filename). Only methodology/architecture/primer/
# sample are indexed - the roadmap is meta-planning, not analyst evidence.
_DOC_SOURCES = [
    ("methodology", "Methodology", "methodology.md"),
    ("architecture", "Architecture", "architecture.md"),
    ("defi-primer", "DeFi mechanics primer", "defi-mechanics-primer.md"),
    ("sample-research", "Sample research brief", "sample-research.md"),
]

# Cap protocols pulled into the live evidence index so a market-wide watchlist
# can't blow up ingest cost; the curated set plus the largest tracked slugs fit.
_MAX_EVIDENCE_PROTOCOLS = 80


def _docs_dir() -> Path | None:
    settings = get_settings()
    if settings.rag_docs_dir:
        p = Path(settings.rag_docs_dir)
        return p if p.is_dir() else None
    # <root>/services/api/app/rag/ingest.py -> parents[4] == repo root (dev);
    # the container copies docs to /app/docs (parents[2] when app is at /app/app).
    here = Path(__file__).resolve()
    for candidate in (here.parents[4] / "docs", here.parents[2] / "docs", Path("docs")):
        if candidate.is_dir():
            return candidate
    return None


def docs_chunks() -> list[Chunk]:
    """Chunk every indexed doc; missing files are skipped (degrade gracefully -
    an image that didn't ship ``docs/`` simply has no doc chunks)."""
    docs_dir = _docs_dir()
    if docs_dir is None:
        logger.info("No docs directory found; indexing protocol evidence only")
        return []
    chunk_size = get_settings().rag_chunk_size
    chunks: list[Chunk] = []
    for doc_id, name, filename in _DOC_SOURCES:
        path = docs_dir / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - fs error is environmental
            logger.warning("Could not read %s: %s", path, exc)
            continue
        chunks.extend(chunk_markdown(doc_id, name, text, chunk_size=chunk_size))
    return chunks


def _overview_lines(pack: ResearchPack) -> list[str]:
    o = pack_to_overview(pack)
    lines = []
    if o.tvl is not None:
        lines.append(f"TVL ${o.tvl:,.0f}")
    if o.change_7d is not None:
        lines.append(f"7d change {o.change_7d:+.1f}%")
    if o.change_30d is not None:
        lines.append(f"30d change {o.change_30d:+.1f}%")
    if o.risk_score is not None:
        lines.append(f"risk score {o.risk_score:.0f}/100 (band {o.risk_band})")
    if o.top_chain:
        share = f"{o.top_chain_share * 100:.0f}%" if o.top_chain_share is not None else "n/a"
        lines.append(f"largest chain {o.top_chain} ({share} of TVL)")
    if o.fees_30d is not None:
        lines.append(f"30d fees ${o.fees_30d:,.0f}")
    lines.extend(_onchain_lines(pack))
    if o.depeg_worst_bps is not None:
        lines.append(
            f"worst stablecoin peg deviation {o.depeg_worst_bps:.0f} bps ({o.depeg_asset})"
        )
    if o.stale_days is not None:
        lines.append(f"data freshness {o.stale_days}d old")
    return lines


def _onchain_lines(pack: ResearchPack) -> list[str]:
    """Two evidence lines about measured contract activity, or nothing at all.

    Only ``ok`` and ``partial`` produce text: an unconfigured or empty provider is
    an absence of evidence, and the chat must not be able to quote "no on-chain
    activity" as if it were a finding. Partial coverage still speaks because the
    chains that did report are real; the missing ones are omitted rather than
    filled with zeros.
    """
    oc = pack.onchain
    if oc is None or oc.status not in ("ok", "partial"):
        return []
    values: list[str] = []
    if oc.active_wallets is not None:
        values.append(f"{oc.active_wallets:,} active wallets")
    if oc.tx_count is not None:
        values.append(f"{oc.tx_count:,} transactions")
    if oc.tx_volume_usd is not None:
        values.append(f"${oc.tx_volume_usd:,.0f} transfer volume")
    if oc.returning_wallets is not None:
        share = (
            f" ({oc.returning_wallet_share * 100:.0f}% of active)"
            if oc.returning_wallet_share is not None
            else ""
        )
        values.append(f"{oc.returning_wallets:,} returning wallets{share}")
    if not values:
        return []
    chains = ", ".join(oc.chains) or "tracked chains"
    return [
        f"on-chain activity {oc.as_of or 'latest day'} on {chains}: " + "; ".join(values),
        "on-chain figures are Dune-measured contract-level activity (distinct "
        "senders to tracked contracts, inbound transfers only), not adjusted for "
        "TVL and not an input to the risk score",
    ]


def chunks_from_pack(pack: ResearchPack, recent_alerts: list[str]) -> list[Chunk]:
    risk = pack.risk
    indicators = (
        [
            {
                "label": i.label,
                "value": i.value,
                "score": i.score,
                "evidence": i.evidence,
                "limitation": i.limitation,
            }
            for i in risk.indicators
        ]
        if risk
        else []
    )
    return chunk_evidence(
        pack.slug,
        pack.detail.name,
        overview_lines=_overview_lines(pack),
        indicators=indicators,
        data_gaps=list(risk.data_gaps) if risk else [],
        recent_alerts=recent_alerts,
        chunk_size=get_settings().rag_chunk_size,
    )


def _tracked_slugs(session: Session) -> list[str]:
    rows = (
        session.query(ProtocolSnapshot.slug)
        .distinct()
        .order_by(ProtocolSnapshot.slug)
        .limit(_MAX_EVIDENCE_PROTOCOLS)
        .all()
    )
    return [r[0] for r in rows]


def _recent_alerts_by_slug(session: Session, limit: int = 5) -> dict[str, list[str]]:
    by_slug: dict[str, list[str]] = defaultdict(list)
    rows = (
        session.query(AlertRecord)
        .order_by(AlertRecord.triggered_at.desc())
        .limit(limit * _MAX_EVIDENCE_PROTOCOLS)
        .all()
    )
    for r in rows:
        if len(by_slug[r.slug]) < limit:
            by_slug[r.slug].append(f"{r.severity}: {r.message}")
    return by_slug


async def build_chunks(
    session: Session, research_service: ProtocolResearchService, http: httpx.AsyncClient
) -> list[Chunk]:
    chunks = docs_chunks()
    alerts_by_slug = _recent_alerts_by_slug(session)
    for slug in _tracked_slugs(session):
        try:
            # The session is threaded through so the pack picks up persisted
            # on-chain activity; without it those evidence lines could never
            # reach the corpus, since only ``run_monitor`` ever calls Dune.
            pack = await research_service.get_pack(slug, http, session=session)
        except Exception as exc:  # noqa: BLE001 - one bad protocol won't sink ingest
            logger.warning("Evidence ingest skipped for %s: %s", slug, type(exc).__name__)
            continue
        chunks.extend(chunks_from_pack(pack, alerts_by_slug.get(slug, [])))
    return chunks


async def reindex(
    session: Session,
    research_service: ProtocolResearchService,
    http: httpx.AsyncClient,
    service,
) -> int:
    """Rebuild the index from docs + live evidence, persist it idempotently,
    and load the result into the service's in-memory ranking. Returns the chunk
    count now available to answer from."""
    if not get_settings().rag_enabled:
        logger.info("RAG disabled; skipping ingest")
        return 0
    chunks = await build_chunks(session, research_service, http)
    # Collapse any chunks sharing an id (the same passage under the same source)
    # so a single flush never tries to insert a duplicate primary key.
    chunks = list({c.id: c for c in chunks}.values())

    existing = {r.chunk_id: r for r in session.query(ChatChunk).all()}
    # Reuse stored embeddings so unchanged text isn't re-embedded (cost + latency).
    for c in chunks:
        row = existing.get(c.id)
        if row is not None and row.embedding is not None:
            c.embedding = list(row.embedding)

    missing = [c for c in chunks if c.embedding is None]
    if missing:
        vectors = await embed_texts([c.text for c in missing], http)
        if vectors:
            for c, vec in zip(missing, vectors, strict=True):
                c.embedding = vec

    # Drop stale rows for sources we just re-indexed (a rewritten section or a
    # refreshed protocol whose indicator text changed) - keeps the index honest.
    covered_docs = {c.doc_id for c in chunks}
    keep_ids = {c.id for c in chunks}
    for cid, row in existing.items():
        if row.doc_id in covered_docs and cid not in keep_ids:
            session.delete(row)

    for c in chunks:
        session.merge(
            ChatChunk(
                chunk_id=c.id,
                doc_id=c.doc_id,
                source_type=c.source_type,
                source_name=c.source_name,
                section=c.section,
                protocol_slug=c.protocol_slug,
                text=c.text,
                embedding=c.embedding,
            )
        )
    session.commit()

    service.index(chunks)
    logger.info("Chat index ready: %d chunks", len(chunks))
    return len(chunks)


def load_index(session: Session, service) -> int:
    """Hydrate the service from already-persisted chunks without re-ingesting
    (used for a fast cold start before the background refresh finishes)."""
    service.load_rows(session.query(ChatChunk).all())
    return service.count
