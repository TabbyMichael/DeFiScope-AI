#!/usr/bin/env python
"""Baseline benchmark + query-plan capture for the protocol catalog (Phase 0).

Measure, then index. This harness exists so the indexing/perf decisions in the
"Database Performance & Indexing" plan are driven by observed numbers, not by a
proposed-index list. It never touches the real application database: by default
it builds its own throwaway SQLite file, seeds a synthetic catalog, and runs the
*real* read functions from ``app.services.catalog`` so the timings reflect the
actual code paths the Explorer and dashboard use.

Run from ``services/api``:

    uv run python scripts/perf_bench.py                       # 5k/50k/100k on SQLite
    uv run python scripts/perf_bench.py --sizes 5000,50000 --iters 200
    uv run python scripts/perf_bench.py --db postgresql+psycopg://user:pw@localhost/perf_scratch
    uv run python scripts/perf_bench.py --out docs/perf-baseline.md

The ``--db`` PostgreSQL target MUST be a scratch database: the script creates the
shared schema and seeds synthetic rows into it (guarded behind ``--confirm-pg``).
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure the package root (services/api) is importable when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import Base, ProtocolCatalog, ProtocolCatalogChain  # noqa: E402
from app.security.principal import Scope  # noqa: E402
from app.services import catalog  # noqa: E402
from sqlalchemy import func, or_, select, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

# Realistic-ish distributions. Categories/chains mirror tests/test_catalog.py.
CATEGORIES = [
    "Lending", "Dexes", "Liquid Staking", "Bridges", "Yield",
    "Stablecoin", "Options", "Restaking", "CEX", "RWA",
]
CHAINS = [
    "Ethereum", "Arbitrum", "Base", "Optimism", "Polygon",
    "Solana", "BNB", "Avalanche", "Gnosis", "Linea",
]
# Brands woven into ~3% of names so an ``ILIKE '%term%'`` search matches a
# realistic small slice (not everything, not nothing) rather than zero rows.
BRANDS = ["Aave", "Compound", "Uniswap", "Curve", "Lido", "Balancer", "Morpho"]
# Risk bands in ascending-score order; the band for a scored row is a coarse
# quartile of its score (mirrors how the scoring engine buckets bands).
BANDS = ["low", "moderate", "elevated", "high"]


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile over an already-sorted latency list (ms)."""
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(round((pct / 100) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def build_engine(db_url: str, *, confirm_pg: bool):  # pragma: no cover - CLI path
    from sqlalchemy import create_engine

    if not db_url.startswith("sqlite"):
        if not confirm_pg:
            sys.exit(
                "Refusing to seed a non-SQLite database without --confirm-pg.\n"
                "Point --db at a SCRATCH Postgres you are willing to have this "
                "script populate (it creates the shared schema and inserts "
                f"synthetic rows). Target: {db_url.split('@')[-1]}"
            )
        return create_engine(db_url)
    # Isolated throwaway file so the real app DB is never touched.
    if db_url == "sqlite":
        db_url = f"sqlite:///{ROOT / 'perf_bench.db'}"
    return create_engine(db_url, connect_args={"check_same_thread": False})


def seed(session, size: int, rng: random.Random) -> None:
    """Bulk-load ``size`` catalog rows (plus chain memberships) with a realistic
    TVL skew and a scored subset, so selectivity resembles the real catalog."""
    session.query(ProtocolCatalogChain).delete()
    session.query(ProtocolCatalog).delete()
    session.commit()

    now = int(time.time())
    now_dt = datetime.now(UTC)
    cat_rows = []
    chain_rows = []
    for i in range(size):
        slug = f"proto-{i:05d}"
        name = f"Proto {i:05d}"
        if i % 30 == 0:  # ~3% carry a brand token for search selectivity
            name = f"{rng.choice(BRANDS)} {name}"
        # Chains: a skew toward 1-3 chains per protocol.
        n_chains = rng.choices([1, 2, 3, 4], weights=[45, 30, 18, 7])[0]
        chains = rng.sample(CHAINS, n_chains)
        # TVL: log-normal-ish so a long tail of large protocols sits at the top
        # of a desc sort (exercises the sort/skip path realistically).
        tvl = round(rng.lognormvariate(20.0, 2.0), 2)
        # ~8% scored, the rest an honest NULL gap (the default Explorer state).
        scored = i % 12 == 0
        risk_score = rng.uniform(0, 100) if scored else None
        band = BANDS[min(3, int((risk_score or 0) // 25))] if scored else None
        updated_dt = now_dt - timedelta(days=rng.randint(0, 90))
        cat_rows.append(
            {
                "slug": slug,
                "name": name[:200],
                "category": rng.choice(CATEGORIES),
                "symbol": f"P{i}",
                "tvl": tvl,
                "change_1d": rng.uniform(-20, 20),
                "change_7d": rng.uniform(-30, 30),
                "change_1m": rng.uniform(-50, 50),
                "audits": rng.choice(["0", "1", "2", "3"]),
                "url": f"https://{slug}.example",
                "listing_timestamp": now - rng.randint(0, 1500) * 86_400,
                "chains": chains,
                "risk_score": round(risk_score, 1) if scored else None,
                "risk_band": band,
                "monitored": 1 if scored else 0,
                "first_seen_at": updated_dt,
                "updated_at": updated_dt,
                "last_synced_at": now_dt,
            }
        )
        for chain in chains:
            chain_rows.append({"slug": slug, "chain": chain})

    _bulk_insert(session, ProtocolCatalog, cat_rows)
    _bulk_insert(session, ProtocolCatalogChain, chain_rows)
    session.commit()


def _bulk_insert(session, model, rows: list[dict], chunk: int = 5_000) -> None:
    if not rows:
        return
    # SQLite grows one bound-param set per statement; chunk well past _CHUNK so a
    # 100k seed stays inside its variable limit without churning the loop.
    from sqlalchemy import insert

    for i in range(0, len(rows), chunk):
        session.execute(insert(model), rows[i : i + chunk])


def make_workloads(session) -> dict[str, Callable[[], object]]:
    """Named read workloads, each calling the REAL catalog function so we time
    production code (count + page included), not a hand-rolled approximation."""

    def default_page():
        return catalog.query_catalog(session, sort="tvl", order="desc", page=1, page_size=25)

    def search():
        return catalog.query_catalog(session, q="aave", sort="tvl", order="desc", page=1, page_size=25)

    def category_filter():
        return catalog.query_catalog(session, category="Lending", page=1, page_size=25)

    def category_band():
        return catalog.query_catalog(session, category="Lending", band="high", page=1, page_size=25)

    def chain_filter():
        return catalog.query_catalog(session, chain="Ethereum", page=1, page_size=25)

    def deep_page():
        # A late offset (~80% through a 25-row paging of the whole catalog).
        total = catalog.catalog_count(session)
        page = max(1, (total // 25) * 4 // 5)
        return catalog.query_catalog(session, sort="tvl", order="desc", page=page, page_size=25)

    def count_only():
        return catalog.catalog_count(session)

    def facets_only():
        return catalog.catalog_facets(session)

    def scoped_page():
        scope = Scope(categories=frozenset({"Lending", "Dexes"}))
        return catalog.query_catalog(session, sort="tvl", order="desc", page=1, page_size=25, scope=scope)

    return {
        "default page (tvl desc)": default_page,
        "search q=aave": search,
        "category filter": category_filter,
        "category + band": category_band,
        "chain filter": chain_filter,
        "deep page (offset)": deep_page,
        "count only": count_only,
        "facets only": facets_only,
        "scoped page (categories)": scoped_page,
    }


def _explain_statements(dialect_name: str) -> dict[str, str]:
    """Representative statements for plan capture, dialect-correct. Compiled from
    SQLAlchemy constructs against the live dialect so binds are literal and the
    SQL matches what the ORM emits for the equivalent workload."""
    p = ProtocolCatalog
    stmts: dict[str, list] = {}

    def order_terms():
        # Mirror catalog._ordering for the default tvl-desc page.
        return [p.tvl.is_(None).asc(), p.tvl.desc(), p.slug.asc()]

    stmts["default page (tvl desc)"] = (
        select(p).order_by(*order_terms()).limit(25).offset(0)
    )
    stmts["search q=aave"] = (
        select(p)
        .where(or_(p.name.ilike("%aave%"), p.slug.ilike("%aave%")))
        .order_by(*order_terms())
        .limit(25)
    )
    stmts["category filter"] = (
        select(p).where(p.category == "Lending").order_by(*order_terms()).limit(25)
    )
    stmts["category + band"] = (
        select(p).where(p.category == "Lending", p.risk_band == "high")
        .order_by(*order_terms()).limit(25)
    )
    stmts["chain filter"] = (
        select(p).where(
            p.slug.in_(
                select(ProtocolCatalogChain.slug).where(
                    ProtocolCatalogChain.chain == "Ethereum"
                )
            )
        ).order_by(*order_terms()).limit(25)
    )
    stmts["count (unfiltered)"] = select(func.count(p.slug))
    stmts["count (category+band)"] = select(func.count(p.slug)).where(
        p.category == "Lending", p.risk_band == "high"
    )

    out: dict[str, str] = {}
    from sqlalchemy.dialects import postgresql, sqlite

    target = postgresql.dialect() if dialect_name == "postgresql" else sqlite.dialect()
    for name, stmt in stmts.items():
        compiled = stmt.compile(
            dialect=target, compile_kwargs={"literal_binds": True}
        )
        out[name] = str(compiled)
    return out


def capture_plans(engine, report_lines: list[str]) -> None:
    dialect = engine.dialect.name
    prefix = (
        "EXPLAIN (ANALYZE, BUFFERS)" if dialect == "postgresql" else "EXPLAIN QUERY PLAN"
    )
    report_lines.append(f"\n## Query plans ({dialect}, `{prefix}`)\n")
    session = sessionmaker(bind=engine)()
    try:
        for name, sql in _explain_statements(dialect).items():
            report_lines.append(f"\n### {name}\n")
            report_lines.append(f"\n```sql\n{sql}\n```\n")
            try:
                rows = session.execute(text(f"{prefix} {sql}")).all()
            except Exception as exc:  # noqa: BLE001 - plan capture is best-effort
                report_lines.append(f"\n```\n(plan unavailable: {type(exc).__name__})\n```\n")
                continue
            lines = [
                " | ".join(str(cell) for cell in tuple(r) if cell is not None)
                for r in rows
            ]
            report_lines.append("```\n" + "\n".join(lines) + "\n```\n")
    finally:
        session.close()


def run(engine, sizes: list[int], iters: int) -> list[str]:
    from sqlalchemy.orm import sessionmaker as sm

    report: list[str] = [
        "# DeFiScope AI — Catalog performance baseline (Phase 0)\n",
        "\nGenerated by `scripts/perf_bench.py`. Latencies in ms. "
        "Each workload runs `iters` times against the real `app.services.catalog` "
        "read functions (page + `COUNT(*)` included).\n",
    ]
    Session = sm(bind=engine)
    rng = random.Random(42)
    for size in sizes:
        session = Session()
        try:
            t_seed = time.perf_counter()
            seed(session, size, rng)
            if engine.dialect.name == "sqlite":
                session.execute(text("ANALYZE"))  # refresh planner stats
            session.commit()
            seed_s = time.perf_counter() - t_seed
            report.append(
                f"\n## Size: {size:,} protocols "
                f"(seeded in {seed_s:.2f}s, dialect `{engine.dialect.name}`)\n"
            )
            report.append(
                "\n| workload | p50 | p95 | p99 | mean |\n|---|---|---|---|---|\n"
            )
            for name, fn in make_workloads(session).items():
                # warmup (page cache), discarded
                for _ in range(5):
                    fn()
                samples: list[float] = []
                for _ in range(iters):
                    t0 = time.perf_counter()
                    fn()
                    samples.append((time.perf_counter() - t0) * 1000.0)
                samples.sort()
                mean = sum(samples) / len(samples)
                p50 = _percentile(samples, 50)
                p95 = _percentile(samples, 95)
                p99 = _percentile(samples, 99)
                report.append(
                    f"| {name} | {p50:.2f} | {p95:.2f} | {p99:.2f} | {mean:.2f} |\n"
                )
                flag = "" if p95 <= 100 else "  ⚠ >100ms p95"
                print(f"  [{size:>7,}] {name:<28} p50={p50:7.2f} p95={p95:7.2f} p99={p99:7.2f}{flag}")
        finally:
            session.close()
        capture_plans(engine, report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Catalog performance baseline harness")
    ap.add_argument("--sizes", default="5000,50000,100000", help="comma-separated row counts")
    ap.add_argument("--iters", type=int, default=200, help="iterations per workload")
    ap.add_argument("--db", default="sqlite", help="'sqlite' (default, throwaway file) or a DB URL")
    ap.add_argument("--confirm-pg", action="store_true", help="required to seed a non-SQLite DB")
    ap.add_argument("--out", default="", help="write the markdown report to this path")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    engine = build_engine(args.db, confirm_pg=args.confirm_pg)
    Base.metadata.create_all(engine)

    print(f"Benchmarking catalog at {sizes} on {engine.dialect.name} (iters={args.iters})")
    report = run(engine, sizes, args.iters)

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("".join(report), encoding="utf-8")
        print(f"Wrote report -> {out_path}")
    else:
        print("\n".join(report))


if __name__ == "__main__":
    main()
