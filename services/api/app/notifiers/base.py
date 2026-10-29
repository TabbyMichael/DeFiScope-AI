"""Pluggable alert delivery primitives.

A :class:`Notifier` is any object with a ``name`` and an ``async send(http,
note)``. Concrete channels live beside this module and are assembled by
``build_notifiers`` from settings. Delivery is deliberately *fire-and-forget*:
a failing channel is logged and skipped so one bad webhook can never abort the
monitoring pass or crash the scheduler, and it never mutates the alert itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.schemas import Alert

# Ordinal severity so a single "min severity" threshold can gate fan-out.
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def severity_at_least(severity: str, minimum: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(minimum, 0)


@dataclass(frozen=True)
class Notification:
    """Channel-agnostic view of one alert, built once per delivery batch so
    every notifier renders the same content in its own format."""

    id: str
    slug: str
    protocol: str
    rule: str
    severity: str
    message: str
    evidence: dict = field(default_factory=dict)
    triggered_at: str = ""

    @classmethod
    def from_alert(cls, a: Alert) -> Notification:
        return cls(
            id=a.id,
            slug=a.slug,
            protocol=a.protocol,
            rule=a.rule,
            severity=a.severity,
            message=a.message,
            evidence=dict(a.evidence),
            triggered_at=a.triggered_at,
        )

    def as_text(self) -> str:
        """Compact single-line body used by chat/email channels."""
        return f"[{self.severity.upper()}] {self.protocol}: {self.message}"

    def as_dict(self) -> dict:
        """Full structured payload for generic JSON webhooks."""
        return {
            "id": self.id,
            "slug": self.slug,
            "protocol": self.protocol,
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
            "triggered_at": self.triggered_at,
        }


class Notifier(Protocol):
    name: str

    async def send(self, http: httpx.AsyncClient, note: Notification) -> None: ...
