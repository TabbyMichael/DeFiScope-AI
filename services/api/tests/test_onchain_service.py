"""On-chain service tests: aggregation, status resolution, and refresh guards.

No network and no Dune key: the client is stubbed and the DB is the local test
SQLite file. What is under test is the *decision layer* - which is where a
number can quietly become a lie (a missing chain summed as if it were zero, a
re-run spending credits, an unconfigured deployment reporting "no activity").
"""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from app.clients.dune import DuneActivityRow, DuneError
from app.config import Settings
from app.db import Base, OnchainObservation, SessionLocal, engine
from app.services import onchain

SLUG = "aave-v3"


def ready_settings(**overrides) -> Settings:
    kwargs = {"dune_api_key": "test-key", "dune_activity_query_id": 42}
    kwargs.update(overrides)
    return Settings(**kwargs)


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def days_ago(n: int) -> str:
    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d")


def row(day: str | date, **metrics) -> DuneActivityRow:
    day = date.fromisoformat(day) if isinstance(day, str) else day
    return DuneActivityRow(day=day, **metrics)


class StubClient:
    """Returns canned rows per chain; records every call it receives."""

    def __init__(self, responses: dict[str, list[DuneActivityRow] | None], errors=()):
        self.responses = responses
        self.errors = set(errors)
        self.calls: list[str] = []

    async def run_activity_query(self, http, chain, addresses, days):
        self.calls.append(chain)
        if chain in self.errors:
            raise DuneError(f"boom on {chain}")
        rows = self.responses.get(chain, [])
        if rows is None:
            return None
        return rows, "exec-1"


class BoomClient:
    """Fails the test if anything asks it for data."""

    async def run_activity_query(self, *args, **kwargs):  # pragma: no cover - asserted
        raise AssertionError("on-chain fetch must not happen when unconfigured")


@pytest.fixture()
def session():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.query(OnchainObservation).delete()
    db.commit()
    try:
        yield db
    finally:
        db.query(OnchainObservation).delete()
        db.commit()
        db.close()


@pytest.fixture()
def mapping(monkeypatch):
    """Replace the curated JSON with the mapping this test needs."""

    def _set(value: dict) -> None:
        monkeypatch.setattr(onchain, "load_dune_mapping", lambda: value)

    return _set


@pytest.fixture(autouse=True)
def reset_rotation(monkeypatch):
    monkeypatch.setattr(onchain, "_rotation", {"offset": 0})


class TestLoad:
    def test_aggregates_chains_for_the_newest_day(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"], "arbitrum": ["0x2"]}})
        day = today()
        session.add_all(
            [
                OnchainObservation(
                    slug=SLUG,
                    chain="ethereum",
                    date=day,
                    active_wallets=100,
                    tx_count=500,
                    tx_volume_usd=1000.0,
                    returning_wallets=40,
                ),
                OnchainObservation(
                    slug=SLUG,
                    chain="arbitrum",
                    date=day,
                    active_wallets=50,
                    tx_count=200,
                    tx_volume_usd=500.5,
                    returning_wallets=10,
                ),
            ]
        )
        session.commit()

        activity = onchain.load(session, SLUG, settings=ready_settings())

        assert activity.status == onchain.OK
        assert activity.as_of == day
        assert activity.chains == ["arbitrum", "ethereum"]
        assert activity.active_wallets == 150
        assert activity.tx_count == 700
        assert activity.tx_volume_usd == 1500.5
        assert activity.returning_wallets == 50
        assert activity.returning_wallet_share == round(50 / 150, 4)
        assert activity.note is None

    def test_missing_chain_is_partial_not_a_smaller_total(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"], "arbitrum": ["0x2"]}})
        session.add(
            OnchainObservation(slug=SLUG, chain="ethereum", date=today(), active_wallets=100)
        )
        session.commit()

        activity = onchain.load(session, SLUG, settings=ready_settings())

        assert activity.status == onchain.PARTIAL
        assert activity.missing_chains == ["arbitrum"]
        assert "arbitrum" in (activity.note or "")
        # The measured chain is still reported - withholding it would hide data.
        assert activity.active_wallets == 100

    def test_old_observation_is_stale_but_still_shown(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"]}})
        session.add(OnchainObservation(slug=SLUG, chain="ethereum", date=days_ago(10), tx_count=7))
        session.commit()

        activity = onchain.load(session, SLUG, settings=ready_settings())

        assert activity.status == onchain.STALE
        assert activity.tx_count == 7
        assert "days old" in (activity.note or "")

    def test_unconfigured_wins_over_persisted_rows(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"]}})
        session.add(OnchainObservation(slug=SLUG, chain="ethereum", date=today(), tx_count=7))
        session.commit()

        activity = onchain.load(
            session, SLUG, settings=ready_settings(dune_api_key=None, dune_activity_query_id=None)
        )

        assert activity.status == onchain.UNCONFIGURED
        assert activity.tx_count is None
        assert "DEFISCOPE_DUNE_API_KEY" in (activity.note or "")

    def test_unmapped_protocol_is_no_data(self, session, mapping):
        mapping({})

        activity = onchain.load(session, SLUG, settings=ready_settings())

        assert activity.status == onchain.NO_DATA
        assert activity.as_of is None

    def test_mapped_but_unfetched_is_no_data(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"]}})

        activity = onchain.load(session, SLUG, settings=ready_settings())

        assert activity.status == onchain.NO_DATA

    def test_share_is_none_when_no_wallets_were_active(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"]}})
        session.add(
            OnchainObservation(
                slug=SLUG, chain="ethereum", date=today(), active_wallets=0, returning_wallets=0
            )
        )
        session.commit()

        activity = onchain.load(session, SLUG, settings=ready_settings())

        # 0/0 is undefined: a 0.0 share would read as "0% returned", a claim.
        assert activity.returning_wallet_share is None


class TestRefresh:
    async def test_writes_rows_then_skips_existing(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"]}})
        stub = StubClient({"ethereum": [row(days_ago(1), tx_count=5), row(today(), tx_count=6)]})

        async with httpx.AsyncClient() as http:
            first = await onchain.refresh(
                session, http, [SLUG], settings=ready_settings(), client=stub
            )
            second = await onchain.refresh(
                session, http, [SLUG], settings=ready_settings(), client=stub
            )

        assert (first.executed, first.written) == (1, 2)
        assert session.query(OnchainObservation).count() == 2
        # The today-row short-circuit: the second pass spends no credits.
        assert (second.executed, second.skipped_existing) == (0, 1)
        assert stub.calls == ["ethereum"]

    async def test_respects_the_per_pass_budget(self, session, mapping):
        mapping({s: {"ethereum": ["0x1"]} for s in ("a", "b", "c")})
        stub = StubClient({"ethereum": [row(today(), tx_count=1)]})

        async with httpx.AsyncClient() as http:
            report = await onchain.refresh(
                session,
                http,
                ["a", "b", "c"],
                settings=ready_settings(dune_max_protocols_per_pass=2),
                client=stub,
            )

        assert report.executed == 2
        assert len({r.slug for r in session.query(OnchainObservation).all()}) == 2

    async def test_one_failing_chain_does_not_erase_the_other(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"], "arbitrum": ["0x2"]}})
        stub = StubClient(
            {"ethereum": [row(today(), tx_count=10)], "arbitrum": []}, errors={"arbitrum"}
        )

        async with httpx.AsyncClient() as http:
            report = await onchain.refresh(
                session, http, [SLUG], settings=ready_settings(), client=stub
            )

        assert report.failed == [f"{SLUG}/arbitrum"]
        stored = session.query(OnchainObservation).all()
        assert [(r.chain, r.tx_count) for r in stored] == [("ethereum", 10)]

    async def test_deferred_execution_writes_nothing(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"]}})
        stub = StubClient({"ethereum": None})

        async with httpx.AsyncClient() as http:
            report = await onchain.refresh(
                session, http, [SLUG], settings=ready_settings(), client=stub
            )

        assert report.deferred == 1
        assert report.written == 0
        assert session.query(OnchainObservation).count() == 0

    async def test_unconfigured_refresh_makes_no_request(self, session, mapping):
        mapping({SLUG: {"ethereum": ["0x1"]}})

        async with httpx.AsyncClient() as http:
            report = await onchain.refresh(
                session,
                http,
                [SLUG],
                settings=ready_settings(dune_api_key=None),
                client=BoomClient(),
            )

        assert report.configured is False
        assert "skipped" in report.summary()
        assert session.query(OnchainObservation).count() == 0

    async def test_protocol_without_a_mapping_is_skipped(self, session, mapping):
        mapping({})
        stub = StubClient({})

        async with httpx.AsyncClient() as http:
            report = await onchain.refresh(
                session, http, [SLUG], settings=ready_settings(), client=stub
            )

        assert stub.calls == []
        assert report.executed == 0
