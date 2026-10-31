"""FastAPI glue for the authorization layer.

Two dependencies cover every protected route:

- ``get_subject`` resolves the caller - ``Authorization: Bearer <token>`` first,
  then the httpOnly cookie - and raises 401 when neither yields a live session.
  In ``auth_mode == "off"`` it returns the synthetic ``ANONYMOUS`` principal so
  the legacy showcase and the historical test suite keep working unchanged.
- ``require(permission)`` composes that with the RBAC gate and raises 403 naming
  the missing verb.

Being dependencies, neither is a boundary on its own: they have to be *applied*
per route, and a route that forgets them is unguarded. That is why the tables in
``docs/architecture.md`` list every path next to its permission.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import User, get_session
from app.security.principal import ANONYMOUS, Subject
from app.security.rbac import has_permission, permissions_for
from app.security.sessions import resolve_session

__all__ = ["enforce", "get_subject", "require", "subject_from_user", "token_from_request"]

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def token_from_request(request: Request) -> str | None:
    """Bearer first, cookie second.

    The cookie exists for a same-origin deployment; the bearer header is what
    the Next server sends, because it is the only credential that survives a
    cross-host API (compose, tunnel).
    """
    header = request.headers.get("authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return request.cookies.get(get_settings().auth_cookie_name) or None


def subject_from_user(user: User) -> Subject:
    return Subject.from_values(
        user_id=user.id,
        email=user.email,
        role=user.role,
        team=user.team,
        clearance=user.clearance or 1,
        allowed_categories=user.allowed_categories,
        allowed_chains=user.allowed_chains,
    )


def _unauthorized(reason: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": "unauthorized", "reason": reason},
        headers=_UNAUTHORIZED_HEADERS,
    )


async def get_subject(request: Request, session: Session = Depends(get_session)) -> Subject:
    if get_settings().auth_mode == "off":
        return ANONYMOUS
    token = token_from_request(request)
    if not token:
        raise _unauthorized("Sign in required.")
    user = resolve_session(session, token)
    if user is None:
        raise _unauthorized("Session is invalid or expired; sign in again.")
    return subject_from_user(user)


def require(permission: str):
    """Dependency factory: a valid subject *and* the named verb."""

    async def _requirement(subject: Subject = Depends(get_subject)) -> Subject:
        if not has_permission(subject, permission):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "forbidden",
                    "policy": "rbac",
                    "reason": f"Role '{subject.role}' does not include '{permission}'.",
                    "failed_predicate": permission,
                    "permission": permission,
                },
            )
        return subject

    return _requirement


def enforce(decision) -> None:
    """Turn a failing policy ``Decision`` into a 403 carrying its reason."""
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.as_detail())


def subject_permissions(subject: Subject) -> list[str]:
    return sorted(permissions_for(subject.role))
