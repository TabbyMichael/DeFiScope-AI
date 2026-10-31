"""Role-based access control: the coarse gate.

A role grants a set of verbs. It says nothing about *which objects* those verbs
apply to - that is the ABAC layer's job (``app.security.policy``). Keeping the
two separate is what lets a new team scope be added without inventing a new role.
"""

from __future__ import annotations

from app.security.principal import Subject

# Verbs used across the API surface.
PROTOCOLS_READ = "protocols:read"
ALERTS_READ = "alerts:read"
BRIEFS_READ = "briefs:read"
BRIEFS_EXPORT = "briefs:export"
CHAT_ASK = "chat:ask"
MONITOR_RUN = "monitor:run"
AUDIT_READ = "audit:read"
USERS_MANAGE = "users:manage"
POLICY_MANAGE = "policy:manage"

ALL_PERMISSIONS = frozenset(
    {
        PROTOCOLS_READ,
        ALERTS_READ,
        BRIEFS_READ,
        BRIEFS_EXPORT,
        CHAT_ASK,
        MONITOR_RUN,
        AUDIT_READ,
        USERS_MANAGE,
        POLICY_MANAGE,
    }
)

_READ_ONLY = frozenset({PROTOCOLS_READ, ALERTS_READ, BRIEFS_READ, CHAT_ASK})

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    # Can look, cannot export, cannot spend compute (no crawl, no downloads).
    "viewer": _READ_ONLY,
    # The desk analyst: adds download + the ability to trigger a monitoring pass.
    "analyst": _READ_ONLY | {BRIEFS_EXPORT, MONITOR_RUN},
    # Adds the audit trail (reserved for the deferred audit-log surface).
    "risk_officer": _READ_ONLY | {BRIEFS_EXPORT, MONITOR_RUN, AUDIT_READ},
    "admin": ALL_PERMISSIONS,
}


def permissions_for(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(subject: Subject, permission: str) -> bool:
    return permission in permissions_for(subject.role)
