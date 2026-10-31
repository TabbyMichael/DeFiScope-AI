"""The demo accounts.

Seeded only when ``auth_mode == "demo"``; ``auth_mode == "required"`` starts
with an empty user table and expects an operator to create accounts out of
band. Each account changes exactly one axis from the one above it, so the
policy layer can be *observed* rather than described:

======  ============  =========  ===================
account role          clearance  data scope
======  ============  =========  ===================
viewer  viewer        1          everything
analyst analyst       1          Lending + Dexes only
officer risk_officer  2          everything (sees critical alerts)
admin   admin         3          everything (bypasses every gate)
======  ============  =========  ===================

The password is published (``auth_demo_password``) because these accounts are
a tour, not a secret. Re-seeding is idempotent: attributes are refreshed on
every start so this table cannot drift from the matrix above.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import User
from app.security.passwords import hash_password, verify_password

__all__ = ["DEMO_USERS", "demo_user_id", "seed_demo_users"]

DEMO_USERS: tuple[dict, ...] = (
    {
        "email": "viewer@demo",
        "display_name": "Vera Viewer",
        "role": "viewer",
        "team": "Research",
        "clearance": 1,
        "allowed_categories": ["*"],
        "allowed_chains": ["*"],
    },
    {
        "email": "analyst@demo",
        "display_name": "Ada Analyst",
        "role": "analyst",
        "team": "Desk",
        "clearance": 1,
        # The one scoped account: proves the ABAC layer is doing work the role
        # alone cannot express.
        "allowed_categories": ["Lending", "Dexes"],
        "allowed_chains": ["*"],
    },
    {
        "email": "officer@demo",
        "display_name": "Omar Officer",
        "role": "risk_officer",
        "team": "Risk",
        "clearance": 2,
        "allowed_categories": ["*"],
        "allowed_chains": ["*"],
    },
    {
        "email": "admin@demo",
        "display_name": "Avery Admin",
        "role": "admin",
        "team": "Platform",
        "clearance": 3,
        "allowed_categories": ["*"],
        "allowed_chains": ["*"],
    },
)


def demo_user_id(email: str) -> str:
    local = email.split("@", 1)[0]
    return f"demo-{local}"


def seed_demo_users(session: Session, *, password: str | None = None) -> int:
    """Upsert the demo accounts. Returns how many rows were created.

    No-op outside demo mode, so a ``required`` deployment never grows accounts
    it did not ask for.
    """
    settings = get_settings()
    if settings.auth_mode != "demo":
        return 0

    secret = password or settings.auth_demo_password
    created = 0
    now = datetime.now(UTC)
    for spec in DEMO_USERS:
        email: str = spec["email"]
        user = session.query(User).filter(User.email == email).one_or_none()
        if user is None:
            user = User(id=demo_user_id(email), email=email, created_at=now)
            session.add(user)
            created += 1
        # Refresh the attribute bag every start: this file is the documentation,
        # and a stale row would misdescribe the policy layer in a demo.
        user.display_name = spec["display_name"]
        user.role = spec["role"]
        user.team = spec["team"]
        user.clearance = spec["clearance"]
        user.allowed_categories = spec["allowed_categories"]
        user.allowed_chains = spec["allowed_chains"]
        user.is_active = 1
        # Hash only when the published password changed (scrypt is deliberately
        # slow, and this runs on every start).
        if not verify_password(secret, user.password_hash):
            user.password_hash = hash_password(secret)
    session.commit()
    return created
