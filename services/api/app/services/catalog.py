"""Protocol discovery catalog: ingestion (sync) and query (paginated reads).

Two responsibilities, both deliberately kept away from the monitoring path:

- ``sync_catalog`` ingests the full DefiLlama ``/protocols`` directory into the
  ``protocol_catalog`` table with idempotent, per-slug upserts. It writes only
  discovery metadata - never a risk score, never a Dune call - so it cannot turn
  into the expensive analytics crawl the scheduler owns.
- ``query_catalog`` serves the paginated/searchable/filterable list the Explorer
  renders entirely from the DB. Sorting uses a fixed allowlist mapped to column
  objects; a caller's ``sort`` string is never interpolated into SQL.

The catalog is far larger than the monitored set, so an item's risk fields are
nullable and stay ``None`` until a scoring pass fills them - the app's honesty
contract (a gap is never a zero) applies to the whole catalog, not only the board.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session

from app.clients.defillama import ProtocolSummary
from app.db import ProtocolCatalog, ProtocolCatalogChain
from app.schemas import CatalogFacets, CatalogSyncStats, ProtocolCatalogItem
from app.security.principal import Scope

logger = logging.getLogger(__name__)

# SQLite caps bound parameters (historically 999); chunk every ``IN`` so a
# five-thousand-row sync neither errors nor emits one giant statement.
_CHUNK = 400

# Sort allowlist: Explorer key -> the column to order by. Anything outside this
# dict is rejected upstream (a Pydantic/FastAPI Literal), so no user string ever
# reaches the query as SQL text - only as a value bound to one of these columns.
SORT_COLUMNS: dict[str, object] = {
    "tvl": ProtocolCatalog.tvl,
    "name": ProtocolCatalog.name,
    "updated": ProtocolCatalog.updated_at,
    "risk": ProtocolCatalog.risk_score,
}

# Nullable numeric sorts push NULLs to the far end regardless of direction, so
# "highest TVL" / "riskiest first" never bury the scored rows under the unscored.
_NULLS_LAST_SORTS = frozenset({"tvl", "risk"})


def _chunks(seq: Sequence, size: int) -> Iterable[Sequence]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _clean(value: object) -> str | None:
    """Trim a string field to ``None`` when blank/non-string."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _opt_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _opt_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _normalize_chains(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for chain in value:
        name = _clean(chain)
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return sorted(out)


def _entry_dict(summary: ProtocolSummary) -> dict | None:
    """Validate + normalize one provider entry into a column dict.

    Returns ``None`` for an unusable row (no slug). Malformed sub-fields degrade
    to ``None``/empty rather than failing the whole entry, matching how the
    DefiLlama client already skips bad rows instead of crashing the crawl."""
    slug = _clean(getattr(summary, "slug", None))
    if not slug:
        return None
    name = _clean(getattr(summary, "name", None)) or slug
    return {
        "slug": slug,
        "name": name[:200],
        "category": _clean(getattr(summary, "category", None)),
        "symbol": _clean(getattr(summary, "symbol", None)),
        "chains": _normalize_chains(getattr(summary, "chains", None)),
        "tvl": _opt_float(getattr(summary, "tvl", None)),
        "change_1d": _opt_float(getattr(summary, "change_1d", None)),
        "change_7d": _opt_float(getattr(summary, "change_7d", None)),
        "change_1m": _opt_float(getattr(summary, "change_1m", None)),
        "audits": _clean(getattr(summary, "audits", None)),
        "url": _clean(getattr(summary, "url", None)),
        "listing_timestamp": _opt_int(getattr(summary, "listing_timestamp", None)),
    }


def normalize_entries(
    summaries: Iterable[ProtocolSummary],
) -> tuple[list[dict], int, int]:
    """Normalize and de-duplicate a provider listing.

    Returns ``(entries, skipped, duplicates)``. De-dupe is by slug and keeps the
    first usable occurrence, so a provider listing that repeats a protocol cannot
    double-insert or race the upsert."""
    by_slug: dict[str, dict] = {}
    skipped = duplicates = 0
    for summary in summaries:
        entry = _entry_dict(summary)
        if entry is None:
            skipped += 1
            continue
        if entry["slug"] in by_slug:
            duplicates += 1
            continue
        by_slug[entry["slug"]] = entry
    return list(by_slug.values()), skipped, duplicates


def _metadata_fields(row: ProtocolCatalog, entry: dict) -> tuple:
    """The tuple of discovery fields that define whether a row actually changed.

    Analysis columns (risk, monitored) are excluded on purpose: they are owned by
    the monitoring pass, so a metadata sync that re-sees an identical protocol is
    an ``unchanged`` no-op even if a score was written since the last sync."""
    return (
        row.name,
        row.category,
        row.symbol,
        row.tvl,
        row.change_1d,
        row.change_7d,
        row.change_1m,
        row.audits,
        row.url,
        row.listing_timestamp,
        list(row.chains or []),
    )


def _apply_metadata(row: ProtocolCatalog, entry: dict, now: datetime, *, touched: bool) -> None:
    """Copy discovery fields onto a row without touching analysis columns."""
    row.name = entry["name"]
    row.category = entry["category"]
    row.symbol = entry["symbol"]
    row.tvl = entry["tvl"]
    row.change_1d = entry["change_1d"]
    row.change_7d = entry["change_7d"]
    row.change_1m = entry["change_1m"]
    row.audits = entry["audits"]
    row.url = entry["url"]
    row.listing_timestamp = entry["listing_timestamp"]
    row.chains = entry["chains"]
    row.last_synced_at = now
    if touched:
        row.updated_at = now


def _load_existing(session: Session, slugs: Sequence[str]) -> dict[str, ProtocolCatalog]:
    existing: dict[str, ProtocolCatalog] = {}
    for chunk in _chunks(slugs, _CHUNK):
        rows = session.query(ProtocolCatalog).filter(ProtocolCatalog.slug.in_(chunk)).all()
        for row in rows:
            existing[row.slug] = row
    return existing


def sync_catalog(
    session: Session,
    summaries: Iterable[ProtocolSummary],
    *,
    now: datetime | None = None,
) -> CatalogSyncStats:
    """Idempotently upsert the normalized directory into the catalog.

    Insert-or-update by slug; rows the provider no longer returns are left in
    place (a delisting must not erase an identity or its stored analysis), and
    analysis columns are never overwritten here. The chain join table is rewritten
    only for protocols whose chain set actually changed, so a steady-state sync
    writes nothing to it."""
    start = time.monotonic()
    stamp = now or datetime.now(UTC)
    entries, skipped, duplicates = normalize_entries(summaries)

    inserted = updated = unchanged = 0
    slugs = [e["slug"] for e in entries]
    existing = _load_existing(session, slugs)
    chain_rewrites: set[str] = set()

    for entry in entries:
        row = existing.get(entry["slug"])
        if row is None:
            row = ProtocolCatalog(slug=entry["slug"], monitored=0, first_seen_at=stamp)
            _apply_metadata(row, entry, stamp, touched=True)
            session.add(row)
            inserted += 1
            chain_rewrites.add(entry["slug"])
        elif _metadata_fields(row, entry) != (
            entry["name"],
            entry["category"],
            entry["symbol"],
            entry["tvl"],
            entry["change_1d"],
            entry["change_7d"],
            entry["change_1m"],
            entry["audits"],
            entry["url"],
            entry["listing_timestamp"],
            entry["chains"],
        ):
            old_chains = list(row.chains or [])
            _apply_metadata(row, entry, stamp, touched=True)
            updated += 1
            if old_chains != entry["chains"]:
                chain_rewrites.add(entry["slug"])
        else:
            row.last_synced_at = stamp
            unchanged += 1

    _rebuild_chains(session, entries, chain_rewrites)

    session.commit()
    total_after = session.query(func.count(ProtocolCatalog.slug)).scalar() or 0
    return CatalogSyncStats(
        fetched=len(list(slugs)),
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        skipped=skipped,
        duplicates=duplicates,
        total_after=int(total_after),
        duration_seconds=round(time.monotonic() - start, 4),
        completed_at=stamp.isoformat(),
    )


def _rebuild_chains(session: Session, entries: list[dict], slugs: set[str]) -> None:
    """Replace (slug, chain) rows for exactly the protocols whose chains moved."""
    if not slugs:
        return
    slug_list = list(slugs)
    for chunk in _chunks(slug_list, _CHUNK):
        session.query(ProtocolCatalogChain).filter(ProtocolCatalogChain.slug.in_(chunk)).delete(
            synchronize_session=False
        )
    by_slug = {e["slug"]: e["chains"] for e in entries if e["slug"] in slugs}
    rows = [{"slug": slug, "chain": chain} for slug, chains in by_slug.items() for chain in chains]
    if rows:
        session.execute(insert(ProtocolCatalogChain), rows)


def _escape_like(term: str) -> str:
    """Neutralize LIKE wildcards so a search term is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ordering(sort: str, order: str) -> list:
    """Build the deterministic ORDER BY from the allowlisted column.

    ``sort`` is already constrained to SORT_COLUMNS by the router's Literal
    validator; we still index the dict rather than trusting the string, so an
    out-of-range key can only ever raise, never form SQL text."""
    column = SORT_COLUMNS[sort]  # type: ignore[index]
    descending = order == "desc"
    clause = column.desc() if descending else column.asc()  # type: ignore[union-attr]
    order_terms: list = []
    if sort in _NULLS_LAST_SORTS:
        # A 0/1 flag column: non-null (0) sorts before null (1) in ascending
        # order, keeping scored rows ahead regardless of value direction.
        order_terms.append(column.is_(None).asc())  # type: ignore[union-attr]
    order_terms.append(clause)
    order_terms.append(ProtocolCatalog.slug.asc())  # stable tiebreak
    return order_terms


def query_catalog(
    session: Session,
    *,
    q: str | None = None,
    chain: str | None = None,
    category: str | None = None,
    band: str | None = None,
    sort: str = "tvl",
    order: str = "desc",
    page: int = 1,
    page_size: int = 25,
    scope: Scope | None = None,
) -> tuple[list[ProtocolCatalogItem], int, int]:
    """Return one page of catalog items plus ``(total, pages)``.

    All filtering, sorting and paging happen in SQL; the caller receives exactly
    ``page_size`` rows. The subject's data scope (when restricted) is applied as
    SQL predicates so ``total`` reflects what the caller may actually see - the
    same "unknown attribute is denied when restricted" rule the board enforces."""
    sort = sort if sort in SORT_COLUMNS else "tvl"
    order = order if order in ("asc", "desc") else "desc"

    query = session.query(ProtocolCatalog)

    if category:
        query = query.filter(ProtocolCatalog.category == category)
    if band:
        # Unmonitored protocols store a NULL band and are presented as "unknown",
        # so filtering by "unknown" must match NULL too - not only rows a scoring
        # pass explicitly wrote a band onto.
        if band == "unknown":
            query = query.filter(
                or_(
                    ProtocolCatalog.risk_band.is_(None),
                    ProtocolCatalog.risk_band == "unknown",
                )
            )
        else:
            query = query.filter(ProtocolCatalog.risk_band == band)
    if chain:
        chain_sub = (
            select(ProtocolCatalogChain.slug)
            .where(ProtocolCatalogChain.chain == chain)
            .scalar_subquery()
        )
        query = query.filter(ProtocolCatalog.slug.in_(chain_sub))

    term = _clean(q)
    if term:
        like = f"%{_escape_like(term)}%"
        query = query.filter(
            or_(
                ProtocolCatalog.name.ilike(like, escape="\\"),
                ProtocolCatalog.slug.ilike(like, escape="\\"),
            )
        )

    if scope is not None and scope.restricted:
        if scope.categories is not None:
            # A null-category row cannot satisfy an ``IN`` and is dropped, which
            # is the intended deny-unknown behaviour.
            query = query.filter(ProtocolCatalog.category.in_(tuple(scope.categories)))
        if scope.chains is not None:
            scope_sub = (
                select(ProtocolCatalogChain.slug)
                .where(ProtocolCatalogChain.chain.in_(tuple(scope.chains)))
                .scalar_subquery()
            )
            query = query.filter(ProtocolCatalog.slug.in_(scope_sub))

    total = query.count()
    pages = (total + page_size - 1) // page_size if page_size else 0
    offset = max(0, (page - 1) * page_size)
    rows = query.order_by(*_ordering(sort, order)).offset(offset).limit(page_size).all()
    return [_row_to_item(r) for r in rows], total, pages


def _row_to_item(row: ProtocolCatalog) -> ProtocolCatalogItem:
    return ProtocolCatalogItem(
        slug=row.slug,
        name=row.name,
        category=row.category,
        symbol=row.symbol,
        chains=list(row.chains or []),
        tvl=row.tvl,
        change_1d=row.change_1d,
        change_7d=row.change_7d,
        change_1m=row.change_1m,
        audits=row.audits,
        url=row.url,
        risk_score=row.risk_score,
        risk_band=row.risk_band or "unknown",
        monitored=bool(row.monitored),
        listing_timestamp=row.listing_timestamp,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


def catalog_facets(session: Session) -> CatalogFacets:
    """Distinct, sorted category and chain values present in the catalog."""
    categories = [
        row[0]
        for row in session.query(ProtocolCatalog.category)
        .filter(ProtocolCatalog.category.isnot(None))
        .distinct()
        .order_by(ProtocolCatalog.category)
        .all()
    ]
    chains = [
        row[0]
        for row in session.query(ProtocolCatalogChain.chain)
        .distinct()
        .order_by(ProtocolCatalogChain.chain)
        .all()
    ]
    return CatalogFacets(categories=categories, chains=chains)


def catalog_count(session: Session) -> int:
    """Total protocols currently stored - used to decide a cold-start sync."""
    return int(session.query(func.count(ProtocolCatalog.slug)).scalar() or 0)


def refresh_analysis(
    session: Session,
    scored: Iterable[tuple[str, float | None, str | None]],
) -> int:
    """Fold monitoring output (risk score / band) back into existing catalog rows.

    The catalog is a read model over monitoring, never a second crawl: this only
    updates ``risk_score`` / ``risk_band`` / ``monitored`` on rows that discovery
    already inserted, and never creates a catalog row or overwrites market
    metadata. A protocol the pass could not score keeps ``risk_score = None``.
    Returns the number of rows touched."""
    touched = 0
    for slug, score, band in scored:
        row = session.get(ProtocolCatalog, slug)
        if row is None:
            continue
        row.risk_score = score
        row.risk_band = band or "unknown"
        row.monitored = 1
        touched += 1
    if touched:
        session.commit()
    return touched


def refresh_analysis_from_snapshots(session: Session) -> int:
    """Fold the newest scored snapshot per protocol back into the catalog.

    Closes the startup ordering gap: if monitoring populated snapshots before a
    catalog sync created the rows, this applies those scores without waiting for
    the next pass. Reads the DB only - no crawl, no provider call."""
    from app.services.dashboard import latest_rows

    scored = [
        (r.slug, r.risk_score, r.risk_band)
        for r in latest_rows(session)
        if r.risk_score is not None
    ]
    return refresh_analysis(session, scored)


async def sync_from_source(
    session: Session, client, http, *, now: datetime | None = None
) -> CatalogSyncStats:
    """Fetch the DefiLlama directory and upsert it - the sync entry point.

    Kept separate from ``sync_catalog`` so the pure upsert stays trivially
    testable without network. This performs exactly one ``/protocols`` read and no
    per-protocol detail, fees or Dune calls: it is discovery metadata, not crawl."""
    summaries = await client.list_protocols(http)
    stats = sync_catalog(session, summaries, now=now)
    # Any directory sync can move metadata, ordering or paging, so retire the
    # cached catalog namespace (bump the version). This is the only way the
    # catalog's discovery columns change, so invalidation here is exact; a no-op
    # when Redis is unconfigured.
    from app.services import cache

    await cache.bump_version()
    return stats


# Shared across the cold-start request path and the startup background task so a
# burst of first-ever requests (or a request racing startup) fills the catalog
# once, not N times, and never races the same primary-key insert.
_fill_lock = asyncio.Lock()


async def ensure_populated(session: Session, client, http) -> None:
    """Fill an empty catalog from the directory, at most once, best-effort.

    A warm catalog short-circuits with a single count and no network, so reads
    stay pure-DB. Respects ``catalog_sync_on_startup``; a disabled or failing
    discovery leaves the catalog empty (a valid, honest empty page) rather than
    blocking a read on an unreachable provider."""
    from app.config import get_settings

    if not get_settings().catalog_sync_on_startup:
        return
    if catalog_count(session):
        return
    async with _fill_lock:
        if catalog_count(session):
            return
        await sync_from_source(session, client, http)
