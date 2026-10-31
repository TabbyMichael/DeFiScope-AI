"""Opaque session tokens and the short-lived WebSocket ticket.

A token is 256 bits of ``secrets`` randomness. The database stores only its
SHA-256, so a leaked dump cannot be replayed as a credential. Sessions are rows
rather than JWTs precisely so that logout is a ``DELETE`` that takes effect on
the next request - no waiting out a signature.

The WebSocket ticket exists because the browser opens ``/ws/chat`` itself and a
socket cannot carry an ``httpOnly`` cookie set on a different host (and a cookie
is host-scoped, not port-scoped, so the published API port is a separate
authorization site). The session is exchanged for a ticket that is single-use,
lives ``auth_ws_ticket_seconds``, and is held in-process: losing it on restart
costs one reconnect and never a credential.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from threading import Lock

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionRecord, User
from app.security.principal import Subject

__all__ = [
    "create_session",
    "hash_token",
    "new_token",
    "resolve_session",
    "revoke_session",
    "tickets",
]


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive timestamps; compare them as UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


# --- sessions ---------------------------------------------------------------


def create_session(
    session: Session, user: User, *, hours: int | None = None
) -> tuple[str, datetime]:
    """Issue a token for ``user``. Returns ``(raw_token, expires_at)``.

    The raw token is returned exactly once and never stored; only its digest
    reaches the database.
    """
    ttl = get_settings().auth_session_hours if hours is None else hours
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=ttl)
    token = new_token()
    session.add(
        SessionRecord(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            expires_at=expires_at,
        )
    )
    session.commit()
    return token, expires_at


def resolve_session(session: Session, token: str | None) -> User | None:
    """Map a token to its active user, or None. Expired rows are reaped here."""
    if not token:
        return None
    record = session.get(SessionRecord, hash_token(token))
    if record is None:
        return None
    expires_at = _aware(record.expires_at)
    if expires_at is None or expires_at <= datetime.now(UTC):
        session.delete(record)
        session.commit()
        return None
    user = session.get(User, record.user_id)
    if user is None or not user.is_active:
        return None
    return user


def revoke_session(session: Session, token: str | None) -> bool:
    """Delete one session row. Returns False when it was already gone."""
    if not token:
        return False
    record = session.get(SessionRecord, hash_token(token))
    if record is None:
        return False
    session.delete(record)
    session.commit()
    return True


# --- WebSocket tickets ------------------------------------------------------


class _TicketStore:
    """In-process, single-use, expiring tickets.

    Deliberately not a table: a ticket's whole life is measured in seconds and
    it must never outlive a restart. ``redeem`` pops before it validates, so a
    replay of the same ticket fails even mid-flight.
    """

    def __init__(self) -> None:
        self._tickets: dict[str, tuple[Subject, datetime]] = {}
        self._lock = Lock()

    def mint(self, subject: Subject) -> tuple[str, int]:
        ttl = max(1, get_settings().auth_ws_ticket_seconds)
        now = datetime.now(UTC)
        ticket = new_token()
        with self._lock:
            self._reap(now)
            self._tickets[ticket] = (subject, now + timedelta(seconds=ttl))
        return ticket, ttl

    def redeem(self, ticket: str | None) -> Subject | None:
        if not ticket:
            return None
        now = datetime.now(UTC)
        with self._lock:
            entry = self._tickets.pop(ticket, None)
            self._reap(now)
        if entry is None:
            return None
        subject, expires_at = entry
        return subject if expires_at > now else None

    def clear(self) -> None:
        with self._lock:
            self._tickets.clear()

    def _reap(self, now: datetime) -> None:
        for key, (_, expires_at) in list(self._tickets.items()):
            if expires_at <= now:
                del self._tickets[key]


tickets = _TicketStore()
