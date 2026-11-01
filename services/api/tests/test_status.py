"""Public coverage aggregates (``GET /api/status``) - no live network.

The contract under test is the null-vs-zero distinction: the landing page
renders ``n/a`` for an unmeasured count and ``0`` for a measured one, and only
these tests keep the two from collapsing into each other.
"""

from datetime import UTC, datetime, timedelta

import pytest
from app.db import (
    AlertRecord,
    Base,
    ChatChunk,
    OnchainObservation,
    ProtocolSnapshot,
    SessionLocal,
    engine,
)
from app.schemas import CoverageStatus
from app.services import status as status_service

NOW = datetime.now(UTC)


@pytest.fixture()
def session():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def snap(slug, date, *, band=None, score=None, category="Lending", chain="Ethereum"):
    return ProtocolSnapshot(
        slug=slug,
        date=date,
        name=slug,
        category=category,
        tvl=1_000.0,
        top_chain=chain,
        risk_score=score,
        risk_band=band,
        captured_at=NOW,
    )


def day(offset: int) -> str:
    """ISO date ``offset`` days back, so ``day(1)`` is newer than ``day(2)``."""
    return (NOW - timedelta(days=offset)).strftime("%Y-%m-%d")


def alert(alert_id, slug, *, severity="warning", hours_ago=0.0):
    return AlertRecord(
        id=alert_id,
        slug=slug,
        protocol=slug,
        rule="tvl_drop",
        severity=severity,
        message="test",
        evidence={},
        triggered_at=(NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds"),
    )


class TestEmptyStore:
    def test_measured_zeros_not_gaps(self, session):
        out = status_service.coverage(session)
        assert out.status == "empty"
        # Nothing stored is a *measurement*, so every count resolves to 0 and
        # none of them is null. This is the case a cold deploy shows.
        assert out.protocols_tracked == 0
        assert out.protocols_scored == 0
        assert out.scored_observations == 0
        assert out.observation_days == 0
        assert out.alerts_total == 0
        assert out.alerts_7d == 0
        assert out.onchain_observations == 0
        assert out.index_chunks == 0
        assert out.captured_at is None  # genuinely nothing captured yet
        assert out.as_of is not None

    def test_bands_and_severity_keys_always_present(self, session):
        out = status_service.coverage(session)
        assert set(out.bands) == set(status_service.BANDS)
        assert set(out.alerts_by_severity) == {"info", "warning", "critical"}
        assert sum(out.bands.values()) == 0

    def test_curated_count_comes_from_settings_not_the_db(self, session):
        from app.config import get_settings

        out = status_service.coverage(session)
        # The store is empty here, so the only honest "what we mean to cover"
        # figure is the configured watchlist, read from settings.
        assert out.protocols_curated == len(get_settings().protocol_slugs)
        assert out.monitor_interval_minutes == get_settings().monitor_interval_minutes


class TestProtocolCoverage:
    def test_counts_distinct_protocols_days_categories_and_chains(self, session):
        session.add_all(
            [
                # aave: scored on both days, newest (day 1) sits in `low`
                snap("aave-v3", day(2), band="moderate", score=41.0),
                snap("aave-v3", day(1), band="low", score=22.0),
                # lido: newest day scored, older day is an unscored backfill row
                snap("lido", day(2), band="elevated"),
                snap("lido", day(1), band="elevated", score=55.0, category="Liquid Staking"),
                # curve: scored on an OLDER day only - must not count as scored
                snap("curve-dex", day(2), band="moderate", score=47.0),
                snap("curve-dex", day(1)),
            ]
        )
        session.add(OnchainObservation(slug="aave-v3", chain="Ethereum", date=day(1), tx_count=10))
        session.add(
            ChatChunk(chunk_id="c1", doc_id="methodology::x", source_type="doc", text="hello")
        )
        session.commit()

        out = status_service.coverage(session)
        assert out.status == "ok"
        assert out.protocols_tracked == 3
        assert out.observation_days == 2
        assert out.categories == 2
        assert out.chains == 1
        # Row-level count is every snapshot that carries a score: six rows,
        # two without one (lido's and curve's older/newest backfill rows).
        assert out.scored_observations == 4
        # Protocol-level count looks at the NEWEST row per slug only, so curve's
        # older scored day does not qualify it.
        assert out.protocols_scored == 2
        assert out.bands == {
            "low": 1,  # aave, from its newest row, not its moderate one
            "moderate": 0,
            "elevated": 1,
            "high": 0,
            "unknown": 1,  # curve's newest row is unscored
        }
        assert out.onchain_observations == 1
        assert out.onchain_protocols == 1
        assert out.onchain_chains == 1
        assert out.index_chunks == 1

    def test_bands_partition_the_latest_snapshot_per_protocol(self, session):
        session.add_all(
            [
                snap("a", day(2), band="low", score=12.0),
                snap("a", day(1), band="high", score=80.0),  # newest wins
                snap("b", day(1), band="low", score=18.0),
                snap("c", day(1), band=None, score=None),  # unscored -> unknown
                snap("d", day(1), band="nonsense", score=5.0),  # unexpected -> unknown
            ]
        )
        session.commit()

        out = status_service.coverage(session)
        assert out.bands["low"] == 1
        assert out.bands["high"] == 1
        assert out.bands["unknown"] == 2
        assert sum(out.bands.values()) == 4
        assert out.protocols_scored == 3


class TestAlertWindow:
    def test_seven_day_filter_and_severity_buckets(self, session):
        session.add_all(
            [
                alert("a1", "a", severity="critical", hours_ago=1),
                alert("a2", "b", severity="warning", hours_ago=24),
                alert(
                    "a3", "c", severity="info", hours_ago=status_service.ALERT_WINDOW_DAYS * 24 + 1
                ),
            ]
        )
        session.commit()

        out = status_service.coverage(session)
        assert out.alerts_total == 3
        assert out.alerts_7d == 2
        assert out.alerts_by_severity == {"info": 1, "warning": 1, "critical": 1}

    def test_missing_timestamp_is_not_counted_as_recent(self, session):
        session.add_all(
            [alert("a1", "a"), AlertRecord(id="a2", slug="b", rule="x", severity="info")]
        )
        session.commit()

        out = status_service.coverage(session)
        assert out.alerts_total == 2
        assert out.alerts_7d == 1


class TestUnavailable:
    def test_store_error_yields_null_counts_not_zeros(self, session, monkeypatch):
        from sqlalchemy.exc import OperationalError

        def boom(_session):
            raise OperationalError("SELECT 1", {}, Exception("database is locked"))

        monkeypatch.setattr(status_service, "_measure", boom)
        out = status_service.coverage(session)

        assert out.status == "unavailable"
        assert out.protocols_tracked is None
        assert out.bands is None
        assert out.alerts_7d is None
        assert out.captured_at is None
        assert out.as_of is None
        # Capability flags do not depend on the store, so they stay truthful.
        from app.config import get_settings

        assert out.protocols_curated == len(get_settings().protocol_slugs)
        assert out.monitor_interval_minutes == get_settings().monitor_interval_minutes

    def test_error_detail_is_never_echoed(self, session, monkeypatch):
        from sqlalchemy.exc import OperationalError

        secret = "postgres://user:pw@host/db"

        def boom(_session):
            raise OperationalError("SELECT 1", {}, Exception(f"{secret} refused"))

        monkeypatch.setattr(status_service, "_measure", boom)
        with pytest.MonkeyPatch.context() as mp:
            captured = []
            mp.setattr(status_service.logger, "warning", lambda *a: captured.append(a))
            out = status_service.coverage(session)

        # The log line is rendered with the recorded args, exactly as a real
        # handler would render it, so this asserts on what an operator sees.
        line = captured[0][0] % captured[0][1:]
        assert secret not in line
        assert line.endswith("OperationalError")
        assert out.status == "unavailable"


class TestEndpoint:
    async def test_status_is_public_and_typed(self, anonymous_client, session):
        session.add_all([snap("a", day(1), band="low", score=20.0)])
        session.commit()

        response = await anonymous_client.get("/api/status")
        assert response.status_code == 200
        body = response.json()
        assert CoverageStatus.model_validate(body).protocols_tracked == 1
        assert body["status"] == "ok"

    async def test_public_even_when_login_is_required(self, settings_demo):
        """The landing page has no session; a secured deploy must not 401 it.

        ``settings_demo`` puts the app in login-required demo mode. ``/api/status``
        takes no subject dependency, so it answers regardless - which is only safe
        because it returns aggregates and no row-level data.
        """
        import httpx
        from app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/status")
        assert response.status_code == 200
        assert response.json()["status"] in {"ok", "empty", "unavailable"}
