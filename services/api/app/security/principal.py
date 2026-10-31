"""The authenticated principal and the data scope it carries.

``Subject`` is the object every authorization check reads. It is a frozen
dataclass built once per request, so a policy function can never accidentally
mutate the caller it is judging.
"""

from __future__ import annotations

from dataclasses import dataclass

WILDCARD = "*"


def _scope_set(values: list[str] | None) -> frozenset[str] | None:
    """Normalize a stored JSON list into a scope set.

    ``None`` and ``["*"]`` both mean unrestricted; an empty list is also
    unrestricted (nothing was configured, so nothing is restricted). A
    non-empty list restricts to exactly those values."""
    if not values:
        return None
    cleaned = {v.strip() for v in values if isinstance(v, str) and v.strip()}
    if not cleaned or WILDCARD in cleaned:
        return None
    return frozenset(cleaned)


@dataclass(frozen=True)
class Scope:
    """The slice of the board a subject may see.

    ``None`` on either axis means unrestricted. An unknown attribute (a protocol
    with no category, or no primary chain) is **denied** when a restriction is
    configured - the same rule the risk model applies to missing data: unknown is
    never silently treated as safe.
    """

    categories: frozenset[str] | None = None
    chains: frozenset[str] | None = None

    @property
    def restricted(self) -> bool:
        return self.categories is not None or self.chains is not None

    def allows_category(self, category: str | None) -> bool:
        if self.categories is None:
            return True
        return bool(category) and category in self.categories

    def allows_chain(self, chain: str | None) -> bool:
        if self.chains is None:
            return True
        return bool(chain) and chain in self.chains

    def allows(self, category: str | None, chain: str | None) -> bool:
        return self.allows_category(category) and self.allows_chain(chain)


@dataclass(frozen=True)
class Subject:
    user_id: str
    email: str
    role: str
    team: str | None = None
    clearance: int = 1
    categories: frozenset[str] | None = None
    chains: frozenset[str] | None = None
    # False for the synthetic principal served while auth_mode == "off".
    authenticated: bool = True

    @property
    def scope(self) -> Scope:
        return Scope(categories=self.categories, chains=self.chains)

    def as_out(self) -> dict:
        """Serializable shape for ``GET /api/auth/me`` and login responses."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role,
            "team": self.team,
            "clearance": self.clearance,
            "categories": sorted(self.categories) if self.categories else [WILDCARD],
            "chains": sorted(self.chains) if self.chains else [WILDCARD],
            "authenticated": self.authenticated,
        }

    @classmethod
    def from_values(
        cls,
        *,
        user_id: str,
        email: str,
        role: str,
        team: str | None = None,
        clearance: int = 1,
        allowed_categories: list[str] | None = None,
        allowed_chains: list[str] | None = None,
        authenticated: bool = True,
    ) -> Subject:
        return cls(
            user_id=user_id,
            email=email,
            role=role,
            team=team,
            clearance=clearance,
            categories=_scope_set(allowed_categories),
            chains=_scope_set(allowed_chains),
            authenticated=authenticated,
        )


# Served only while auth_mode == "off": everything is permitted, nothing is
# attributed. Exists so the legacy showcase and the historical test suite keep
# working without pretending to be secure.
ANONYMOUS = Subject(
    user_id="anonymous",
    email="anonymous@local",
    role="admin",
    clearance=3,
    authenticated=False,
    categories=None,
    chains=None,
)

DEMO_PASSWORD_DEFAULT = "defiscope-demo"

__all__ = ["ANONYMOUS", "Scope", "Subject", "WILDCARD"]
