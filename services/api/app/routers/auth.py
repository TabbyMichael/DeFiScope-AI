"""Authentication endpoints: log in, log out, who am I, and the WS ticket.

The enforcement decision this file encodes: the API - not the Next server - is
the authority. The browser reaches `/api` and `/ws` directly in two ways that no
middleware can guard (the published port and the WebSocket), so a credential
that only exists in a Next cookie would be a lock on the wrong door. The web app
holds the token in an ``httpOnly`` cookie and forwards it as a bearer token;
every gate below is enforced here regardless of what the UI does.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import User, get_session
from app.schemas import LoginRequest, LoginResponse, SubjectOut, SwitchRequest, TicketResponse
from app.security import sessions
from app.security.deps import get_subject, require, subject_from_user, token_from_request
from app.security.passwords import hash_password, verify_password
from app.security.principal import Subject
from app.security.rbac import CHAT_ASK, permissions_for
from app.security.seed import DEMO_USERS

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for every credential failure. Distinguishing "no such account"
# would turn the login form into an account-enumeration oracle.
_BAD_CREDENTIALS = "Email or password is incorrect"


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Verified against when the email is unknown, so a failed login costs the
    same scrypt work either way and the response time does not leak existence."""
    return hash_password(sessions.new_token())


def subject_out(subject: Subject) -> SubjectOut:
    return SubjectOut(**subject.as_out(), permissions=sorted(permissions_for(subject.role)))


def _issue(session: Session, user: User) -> LoginResponse:
    token, expires_at = sessions.create_session(session, user)
    return LoginResponse(
        token=token,
        subject=subject_out(subject_from_user(user)),
        expires_at=expires_at.isoformat(),
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    email = body.email.strip().lower()
    user = session.query(User).filter(User.email == email).one_or_none()
    encoded = user.password_hash if user is not None else _dummy_hash()
    password_ok = verify_password(body.password, encoded)
    if user is None or not password_ok or not user.is_active:
        raise HTTPException(status_code=401, detail=_BAD_CREDENTIALS)
    return _issue(session, user)


@router.post("/logout")
def logout(request: Request, session: Session = Depends(get_session)):
    """Delete the session row. Idempotent: an already-dead token is not an error,
    because the caller's intent (be logged out) is satisfied either way."""
    revoked = sessions.revoke_session(session, token_from_request(request))
    return {"ok": True, "revoked": revoked}


@router.get("/me", response_model=SubjectOut)
async def me(subject: Subject = Depends(get_subject)):
    return subject_out(subject)


@router.post("/switch", response_model=LoginResponse)
def switch(
    body: SwitchRequest,
    request: Request,
    session: Session = Depends(get_session),
    subject: Subject = Depends(get_subject),
):
    """Demo only: become another seeded account without typing a password.

    Disabled in ``required`` mode - impersonation is a tour affordance, not a
    feature of a real deployment. The caller's previous session is revoked so
    the switch is an identity transition rather than a second live credential.
    """
    if get_settings().auth_mode != "demo":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "policy": "auth.switch",
                "reason": "Role switching is only available in demo mode.",
                "failed_predicate": "auth_mode",
            },
        )
    email = body.email.strip().lower()
    if email not in {u["email"] for u in DEMO_USERS}:
        raise HTTPException(status_code=404, detail="No such demo account")
    user = session.query(User).filter(User.email == email).one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="No such demo account")

    sessions.revoke_session(session, token_from_request(request))
    return _issue(session, user)


@router.post("/ticket", response_model=TicketResponse)
async def ws_ticket(subject: Subject = Depends(require(CHAT_ASK))):
    """Mint a single-use, short-lived credential for the browser's WebSocket.

    Gated on ``chat:ask`` so the ticket can never out-rank the verb that
    matters: a role that cannot ask questions cannot get a socket either.
    """
    if not subject.authenticated:
        # auth_mode == "off": the socket accepts the connection without a ticket.
        return TicketResponse(ticket="", expires_in=0)
    ticket, ttl = sessions.tickets.mint(subject)
    return TicketResponse(ticket=ticket, expires_in=ttl)


__all__ = ["router", "subject_out", "CHAT_ASK"]
