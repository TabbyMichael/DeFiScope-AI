"""DB-first protocol detail assembly (no DefiLlama crawl on the read path).

The detail route used to rebuild the payload by crawling; it now reads only
snapshots/catalog/on-chain rows. These tests pin the three read states and the
honesty contract: a captured protocol renders its stored analysis, a listed-but-
uncaptured one renders catalog metadata with gap fields (never zeros), and a slug
in neither table is a genuine not-found - not a masked "no data yet".
"""

from datetime import UTC, datetime

import pytest
from app.db import Base, ProtocolCatalog, ProtocolSnapshot, SessionLocal, engine
from app.services import detail


@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for row in session.query(ProtocolSnapshot).filter(
            ProtocolSnapshot.slug.in_(["seeded-protocol", "listed-only"])
        ).all():
            session.delete(row)
        for slug in ("seeded-protocol", "listed-only"):
            session.query(ProtocolCatalog).filter_by(slug=slug).delete()
        session.commit()
        session.close()


def _risk_dict(slug: str) -> dict:
    return {
        "slug": slug,
        "composite_score": 42.0,
        "band": "moderate",
        "indicators": [
            {
                "key": "tvl_volatility",
                "label": "TVL volatility",
                "value": 0.05,
                "score": 30.0,
                "weight": 0.2,
                "evidence": "30d std-dev 5%",
                "limitation": "USD TVL conflates price with usage",
            }
        ],
        "data_gaps": ["real_yield_dependence"],
    }


def _snapshot(slug: str, date: str, **kw) -> ProtocolSnapshot:
    base = dict(
        slug=slug,
        date=date,
        name="Seeded Protocol",
        category="Lending",
        tvl=1_000_000.0,
        change_7d=3.0,
        change_30d=8.0,
        captured_at=datetime.now(UTC),
        monitored=1,
    )
    base.update(kw)
    return ProtocolSnapshot(**base)


def test_seeded_snapshot_renders_full_payload(db):
    db.add_all(
        [
            _snapshot("seeded-protocol", "2026-01-01", tvl=900_000.0),
            _snapshot("seeded-protocol", "2026-01-02", tvl=1_000_000.0),
            _snapshot(
                "seeded-protocol",
                "2026-01-03",
                risk_score=42.0,
                risk_band="moderate",
                fees_1d=1200.0,
                fees_30d=30000.0,
                revenue_1d=400.0,
                top_chain="Ethereum",
                top_chain_share=0.7,
                chain_shares={"Ethereum": 700_000, "Arbitrum": 300_000},
                risk_json=_risk_dict("seeded-protocol"),
            ),
        ]
    )
    db.add(
        ProtocolCatalog(
            slug="seeded-protocol",
            name="Seeded Protocol",
            category="Lending",
            url="https://seeded.example",
            tvl=1_000_000.0,
        )
    )
    db.commit()

    pack = detail.load_detail(db, "seeded-protocol")

    assert pack.overview.source == "db"
    assert pack.overview.risk_band == "moderate"
    assert pack.overview.fees_30d == 30000.0
    # The URL comes from the catalog row even though analysis came from the row.
    assert pack.url == "https://seeded.example"
    # One point per persisted TVL day, ascending.
    assert [p.date for p in pack.tvl_series] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    # Chain breakdown re-derived from stored shares, largest first.
    assert [(c.chain, c.share) for c in pack.chains] == [("Ethereum", 0.7), ("Arbitrum", 0.3)]
    assert pack.risk["composite_score"] == 42.0
    assert pack.data_gaps == ["real_yield_dependence"]

    research = detail.to_research(pack)
    assert research.risk.composite_score == 42.0
    assert research.risk.indicators[0].key == "tvl_volatility"
    assert research.slug == "seeded-protocol"


def test_listed_only_protocol_renders_gap_fields(db):
    # A catalog row with no snapshot: the honest gap-only page.
    db.add(
        ProtocolCatalog(
            slug="listed-only",
            name="Listed Only",
            category="Dexes",
            tvl=500.0,
            change_7d=2.5,
        )
    )
    db.commit()

    pack = detail.load_detail(db, "listed-only")

    assert pack.overview.source == "catalog"
    assert pack.overview.tvl == 500.0
    assert pack.overview.risk_band == "unknown"
    # Analysis the page could not have measured stays null - never a fabricated 0.
    assert pack.overview.fees_30d is None
    assert pack.overview.risk_score is None
    assert pack.risk is None
    assert pack.tvl_series == []
    assert pack.chains == []

    research = detail.to_research(pack)
    # The risk block is present but empty (not a low score), and the on-chain
    # block reports its own gap status rather than being dropped.
    assert research.risk.composite_score is None
    assert research.risk.indicators == []
    assert research.data_gaps == []
    assert research.onchain.status in {"no_data", "unconfigured"}


def test_unknown_slug_raises_not_found(db):
    with pytest.raises(detail.ProtocolUnknown):
        detail.load_detail(db, "no-such-protocol-anywhere")
