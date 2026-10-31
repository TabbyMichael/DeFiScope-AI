"""Authentication: login, logout, identity, the mode ladder and the WS ticket.

Runs in ``auth_mode="demo"`` (see the ``settings_demo`` fixture), because the
whole point of these tests is that a credential is *required* - the legacy
"off" posture is asserted separately at the bottom.
"""

import time

from app.config import get_settings
from app.security import sessions
from app.security.principal import ANONYMOUS, Subject

DEMO_PASSWORD = "defiscope-demo"


def _login_body(email: str, password: str = DEMO_PASSWORD) -> dict:
    return {"email": email, "password": password}


class TestLogin:
    async def test_login_returns_a_token_and_the_resolved_subject(
        self, settings_demo, anonymous_client
    ):
        resp = await anonymous_client.post("/api/auth/login", json=_login_body("analyst@demo"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["token"]
        assert body["expires_at"]
        subject = body["subject"]
        assert subject["email"] == "analyst@demo"
        assert subject["role"] == "analyst"
        assert subject["clearance"] == 1
        # The scope is returned so the UI can explain itself without a second call.
        assert subject["categories"] == ["Dexes", "Lending"]
        # And the resolved verbs, so a control can be disabled rather than 403'd.
        assert "briefs:export" in subject["permissions"]
        assert "monitor:run" in subject["permissions"]

    async def test_login_is_case_and_whitespace_insensitive(self, settings_demo, anonymous_client):
        resp = await anonymous_client.post("/api/auth/login", json=_login_body("  VIEWER@demo  "))
        assert resp.status_code == 200
        assert resp.json()["subject"]["email"] == "viewer@demo"

    async def test_wrong_password_and_unknown_email_are_indistinguishable(
        self, settings_demo, anonymous_client
    ):
        wrong = await anonymous_client.post(
            "/api/auth/login", json=_login_body("viewer@demo", "nope")
        )
        unknown = await anonymous_client.post("/api/auth/login", json=_login_body("nobody@demo"))
        assert wrong.status_code == unknown.status_code == 401
        # An enumeration oracle is one of the cheapest bugs to ship; assert the
        # two answers are byte-identical, message included.
        assert wrong.json() == unknown.json()


class TestSessionLifecycle:
    async def test_me_requires_a_credential(self, settings_demo, anonymous_client):
        resp = await anonymous_client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"

    async def test_me_returns_the_caller(self, settings_demo, viewer_client):
        resp = await viewer_client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "viewer@demo"
        assert resp.json()["authenticated"] is True

    async def test_logout_revokes_the_session_immediately(self, settings_demo, viewer_client):
        assert (await viewer_client.get("/api/auth/me")).status_code == 200
        assert (await viewer_client.post("/api/auth/logout")).status_code == 200
        # Same client, same token: the delete must take effect on the next call.
        assert (await viewer_client.get("/api/auth/me")).status_code == 401

    async def test_logout_is_idempotent(self, settings_demo, viewer_client):
        await viewer_client.post("/api/auth/logout")
        again = await viewer_client.post("/api/auth/logout")
        assert again.status_code == 200
        assert again.json()["revoked"] is False

    async def test_a_garbage_token_is_401_not_500(self, settings_demo, anonymous_client):
        resp = await anonymous_client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert resp.status_code == 401

    async def test_only_the_token_digest_is_stored(self, settings_demo, auth_headers):
        from app.db import SessionLocal, SessionRecord

        headers = auth_headers("viewer@demo")
        raw = headers["Authorization"].split(" ", 1)[1]
        db = SessionLocal()
        try:
            assert db.get(SessionRecord, raw) is None  # raw token never persisted
            assert db.get(SessionRecord, sessions.hash_token(raw)) is not None
        finally:
            db.close()


class TestRoleSwitch:
    async def test_switch_reissues_a_session_for_another_demo_account(
        self, settings_demo, viewer_client
    ):
        resp = await viewer_client.post("/api/auth/switch", json={"email": "officer@demo"})
        assert resp.status_code == 200
        assert resp.json()["subject"]["role"] == "risk_officer"
        # The previous session is revoked: switching is a transition, not a copy.
        assert (await viewer_client.get("/api/auth/me")).status_code == 401

    async def test_switch_rejects_an_account_that_is_not_seeded(self, settings_demo, viewer_client):
        resp = await viewer_client.post("/api/auth/switch", json={"email": "ceo@corp"})
        assert resp.status_code == 404

    async def test_switch_is_disabled_outside_demo_mode(self, settings_demo, monkeypatch):
        import httpx
        from app.db import SessionLocal, User
        from app.main import app

        monkeypatch.setattr(settings_demo, "auth_mode", "required")
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == "viewer@demo").one()
            token, _ = sessions.create_session(db, user)
        finally:
            db.close()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.post("/api/auth/switch", json={"email": "admin@demo"})
        assert resp.status_code == 403
        assert resp.json()["detail"]["policy"] == "auth.switch"


class TestWebSocketTicket:
    def test_ticket_is_single_use(self, settings_demo):
        ticket, ttl = sessions.tickets.mint(ANONYMOUS)
        assert ttl > 0
        assert sessions.tickets.redeem(ticket) is not None
        # Replay fails even though the TTL has not elapsed.
        assert sessions.tickets.redeem(ticket) is None

    def test_unknown_and_empty_tickets_are_refused(self, settings_demo):
        assert sessions.tickets.redeem(None) is None
        assert sessions.tickets.redeem("") is None
        assert sessions.tickets.redeem("never-issued") is None

    def test_ticket_expires(self, settings_demo, monkeypatch):
        monkeypatch.setattr(settings_demo, "auth_ws_ticket_seconds", 1)
        ticket, ttl = sessions.tickets.mint(ANONYMOUS)
        assert ttl == 1
        time.sleep(1.05)
        assert sessions.tickets.redeem(ticket) is None

    async def test_ticket_endpoint_requires_a_session(self, settings_demo, anonymous_client):
        assert (await anonymous_client.post("/api/auth/ticket")).status_code == 401

    async def test_ticket_endpoint_mints_for_a_signed_in_subject(
        self, settings_demo, viewer_client
    ):
        resp = await viewer_client.post("/api/auth/ticket")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticket"]
        assert sessions.tickets.redeem(body["ticket"]) is not None


class TestModeLadder:
    """``off`` must stay the open legacy posture; ``demo`` must close the door."""

    async def test_off_mode_serves_a_synthetic_privileged_principal(
        self, anonymous_client, monkeypatch
    ):
        # conftest defaults to off; assert it explicitly so the ladder is pinned.
        monkeypatch.setattr(get_settings(), "auth_mode", "off")
        resp = await anonymous_client.get("/api/auth/me")
        assert resp.status_code == 200
        subject = resp.json()
        assert subject["role"] == "admin"
        assert subject["authenticated"] is False

    async def test_demo_mode_refuses_unauthenticated_protected_routes(
        self, settings_demo, anonymous_client
    ):
        # The exact hole this work closes: the published API port.
        for method, path in [
            ("get", "/api/dashboard"),
            ("get", "/api/alerts"),
            ("post", "/api/alerts/run"),
            ("get", "/api/protocols"),
        ]:
            resp = await getattr(anonymous_client, method)(path)
            assert resp.status_code == 401, path

    async def test_health_stays_public_in_demo_mode(self, settings_demo, anonymous_client):
        assert (await anonymous_client.get("/api/health")).status_code == 200

    def test_off_mode_principal_is_not_authenticated(self):
        assert ANONYMOUS.authenticated is False
        assert ANONYMOUS.clearance == 3
        assert isinstance(ANONYMOUS, Subject)
