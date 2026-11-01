"""Isolate tests from the developer's local SQLite file."""

import os

os.environ.setdefault("DEFISCOPE_DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("DEFISCOPE_OPENAI_API_KEY", "")
os.environ.setdefault("DEFISCOPE_DEFAULT_PROTOCOLS", "test-protocol")
# Keep integration tests on the curated list only; watchlist discovery is
# covered separately in test_watchlist.py.
os.environ.setdefault("DEFISCOPE_MARKET_TOP_N", "0")
# Authorization is OFF by default so the pre-existing suite keeps asserting on
# *data* rather than on credentials - every request is served the synthetic
# ANONYMOUS principal, exactly the posture those tests were written against.
# The auth/RBAC/ABAC suites opt into demo mode via the ``settings_demo`` fixture.
os.environ.setdefault("DEFISCOPE_AUTH_MODE", "off")
# No Dune credential by default: on-chain analytics must degrade to an explicit
# data gap, and no test may reach out to api.dune.com because a developer happens
# to have a key in services/api/.env.
os.environ.setdefault("DEFISCOPE_DUNE_API_KEY", "")
# No Redis URL by default: the catalog cache is a no-op in tests, so every read
# hits the test database. The cache logic is exercised separately with an
# injected fake client. Mirrors the Dune guard - a developer's .env can never
# make CI reach a live Redis.
os.environ.setdefault("DEFISCOPE_REDIS_URL", "")

import httpx  # noqa: E402
import pytest  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, User, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import sessions  # noqa: E402
from app.security.seed import seed_demo_users  # noqa: E402
from app.services.protocols import ProtocolResearchService  # noqa: E402


@pytest.fixture()
def settings_demo():
    """Run one test against ``auth_mode="demo"`` with the seeded accounts.

    ``get_settings`` is cached, so the mode is flipped on the instance (every
    consumer reads it at call time) and restored afterwards. Nothing here
    touches the real environment, so tests stay order-independent.
    """
    settings = get_settings()
    previous = settings.auth_mode
    settings.auth_mode = "demo"
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_demo_users(db)
    finally:
        db.close()
    yield settings
    settings.auth_mode = previous


@pytest.fixture()
def auth_headers(settings_demo):
    """``auth_headers("analyst@demo")`` -> a bearer header for that account."""
    issued: list[str] = []

    def _headers(email: str) -> dict[str, str]:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).one()
            token, _ = sessions.create_session(db, user)
        finally:
            db.close()
        issued.append(token)
        return {"Authorization": f"Bearer {token}"}

    yield _headers

    # Leave no sessions behind: a later test asserting on table contents would
    # otherwise see rows from this one.
    db = SessionLocal()
    try:
        for token in issued:
            sessions.revoke_session(db, token)
    finally:
        db.close()


async def _client(headers: dict[str, str] | None = None) -> httpx.AsyncClient:
    """An ASGI client with the app state a lifespan would normally provide."""
    app.state.http = httpx.AsyncClient()
    app.state.research_service = ProtocolResearchService()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=headers or {}
    )


@pytest.fixture()
async def anonymous_client():
    client = await _client()
    try:
        yield client
    finally:
        await client.aclose()
        await app.state.http.aclose()


@pytest.fixture()
async def viewer_client(auth_headers):
    client = await _client(auth_headers("viewer@demo"))
    try:
        yield client
    finally:
        await client.aclose()
        await app.state.http.aclose()


@pytest.fixture()
async def analyst_client(auth_headers):
    """The one scoped account: ``Lending`` + ``Dexes`` only."""
    client = await _client(auth_headers("analyst@demo"))
    try:
        yield client
    finally:
        await client.aclose()
        await app.state.http.aclose()


@pytest.fixture()
async def officer_client(auth_headers):
    client = await _client(auth_headers("officer@demo"))
    try:
        yield client
    finally:
        await client.aclose()
        await app.state.http.aclose()


@pytest.fixture()
async def admin_client(auth_headers):
    client = await _client(auth_headers("admin@demo"))
    try:
        yield client
    finally:
        await client.aclose()
        await app.state.http.aclose()
