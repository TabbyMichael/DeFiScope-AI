"""The attribute layer: predicates evaluated *after* the RBAC gate.

Pure functions, zero I/O - the whole matrix is testable without a database,
which is the discipline ``analysis/metrics.py`` already follows. Every
predicate returns a :class:`Decision` instead of raising, because a denial has
three legitimate shapes depending on the caller:

* a 403 naming the failing attribute (detail views, exports, manual runs);
* a *withheld count* while the rest of the feed still renders (alerts);
* a disabled control with the reason inline (the web UI).

The one shape that is never acceptable is a silent empty list. A denial has to
say which rule fired and what would satisfy it, or the reader cannot tell
"nothing to show" from "you are not allowed to see it" - exactly the honesty
contract the risk model applies to missing data.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time

from app.schemas import Alert
from app.security.principal import Subject

# Policy ids double as the ``policy`` field of a denial and as the label the UI
# shows. Stable strings, so a doc line and a log line refer to the same rule.
SCOPE = "scope.category_chain"
ALERT_CLEARANCE = "alerts.severity_clearance"
BRIEF_CONFIDENCE = "briefs.export.confidence_gate"
MONITOR_FRESHNESS = "monitor.run.freshness"
MONITOR_HOURS = "monitor.run.business_hours"

# Roles that may sign off on a low-confidence brief or force a monitoring pass.
SIGNOFF_ROLES = frozenset({"risk_officer", "admin"})
ADMIN_ROLE = "admin"

# Critical evidence requires clearance 2: seeing *that* something broke is a
# different right from seeing *what* broke, and the count is still shown.
CRITICAL_CLEARANCE = 2
CRITICAL_SEVERITY = "critical"

# Manual monitoring passes are a business-hours action. Local server time is
# the reference clock; the container runs UTC, so the window is UTC in compose.
BUSINESS_START = time(7, 0)
BUSINESS_END = time(22, 0)
WEEKEND = 5  # datetime.weekday(): Mon=0 .. Sat=5


@dataclass(frozen=True)
class Decision:
    """The outcome of one predicate, including why and which rule fired.

    ``failed_predicate`` is the machine-readable half of the reason: it names
    the attribute that could not be satisfied (``category``, ``clearance``,
    ``data_freshness_hours``), so a client can highlight the right control
    without parsing prose.
    """

    allowed: bool
    policy: str
    reason: str
    failed_predicate: str | None = None

    def as_detail(self) -> dict:
        """Body for a ``HTTPException(403, detail=...)``."""
        return {
            "error": "forbidden",
            "policy": self.policy,
            "reason": self.reason,
            "failed_predicate": self.failed_predicate,
        }


def allow(policy: str, reason: str) -> Decision:
    return Decision(True, policy, reason, None)


def deny(policy: str, reason: str, failed_predicate: str | None = None) -> Decision:
    return Decision(False, policy, reason, failed_predicate)


# --- scope.category_chain ---------------------------------------------------


def check_scope(
    subject: Subject, *, category: str | None, chain: str | None, resource: str = "This protocol"
) -> Decision:
    """Is the resource inside the subject's data scope?

    Both axes must pass. An unrestricted axis (``None`` scope) passes for
    everything; a *restricted* axis denies an unknown attribute, so a row with
    no category can never leak past a category filter.
    """
    scope = subject.scope
    if not scope.restricted:
        return allow(SCOPE, "Subject is not limited to a data scope")

    if not scope.allows_category(category):
        covered = ", ".join(sorted(scope.categories or ())) or "none"
        return deny(
            SCOPE,
            f"{resource} is outside your category scope: "
            f"{category or 'no category'} is not in [{covered}].",
            "category",
        )
    if not scope.allows_chain(chain):
        covered = ", ".join(sorted(scope.chains or ())) or "none"
        return deny(
            SCOPE,
            f"{resource} is outside your chain scope: "
            f"{chain or 'no primary chain'} is not in [{covered}].",
            "top_chain",
        )
    return allow(SCOPE, "Resource is inside the subject's data scope")


# --- alerts.severity_clearance ---------------------------------------------


def check_alert_visibility(subject: Subject, *, severity: str) -> Decision:
    """Critical alerts need clearance 2; everything else is readable.

    The caller withholds the *content* but keeps the *count*, so a clearance-1
    analyst still learns that three critical events occurred - the app never
    reports "no alerts" when alerts exist.
    """
    if severity != CRITICAL_SEVERITY or subject.clearance >= CRITICAL_CLEARANCE:
        return allow(ALERT_CLEARANCE, "Clearance covers this severity")
    return deny(
        ALERT_CLEARANCE,
        f"Critical alerts withheld - clearance {CRITICAL_CLEARANCE} required "
        f"(you have {subject.clearance}).",
        "clearance",
    )


def split_visible_alerts(
    alerts: Iterable[Alert],
    subject: Subject,
    *,
    visible_slugs: set[str] | None = None,
) -> tuple[list[Alert], int]:
    """Split a feed into (what this subject may read, how many were withheld).

    ``visible_slugs`` applies the data scope: an alert for a protocol outside
    the scope is not *withheld* (a clearance request would not reveal it), it
    is simply not the subject's business, so it is neither shown nor counted.
    """
    visible: list[Alert] = []
    withheld = 0
    for alert in alerts:
        if visible_slugs is not None and alert.slug not in visible_slugs:
            continue
        if check_alert_visibility(subject, severity=alert.severity).allowed:
            visible.append(alert)
        else:
            withheld += 1
    return visible, withheld


# --- briefs.export.confidence_gate -----------------------------------------


def check_brief_export(
    subject: Subject, *, confidence: str, data_gaps: Iterable[str] = ()
) -> Decision:
    """A low-confidence brief may be read but not leave the building unsigned.

    Export is the point where a caveated document becomes a number in someone
    else's deck, so the gate sits on the download, not the read.
    """
    if confidence != "low" or subject.role in SIGNOFF_ROLES:
        return allow(BRIEF_CONFIDENCE, "Export carries sufficient confidence")
    gaps = len(list(data_gaps))
    plural = "" if gaps == 1 else "s"
    return deny(
        BRIEF_CONFIDENCE,
        f"Brief confidence is low ({gaps} data gap{plural}); export needs risk-officer sign-off.",
        "confidence",
    )


# --- monitor.run.freshness / monitor.run.business_hours --------------------


def check_monitor_freshness(
    subject: Subject, *, freshness_hours: float | None, stale_after_hours: float | None = None
) -> Decision:
    """Refuse a crawl that cannot produce anything new.

    ``freshness_hours`` is None when nothing has been captured yet (a crawl is
    then exactly what is needed). Admins can always force a pass - they are the
    escape hatch when the board looks wrong despite a fresh timestamp.
    """
    from app.services.dashboard import STALE_AFTER  # local: keeps policy I/O-free at import

    if subject.role == ADMIN_ROLE:
        return allow(MONITOR_FRESHNESS, "Admin may force a pass")
    limit = (
        stale_after_hours if stale_after_hours is not None else STALE_AFTER.total_seconds() / 3600
    )
    if freshness_hours is None:
        return allow(MONITOR_FRESHNESS, "No snapshot captured yet")
    if freshness_hours > limit:
        return allow(MONITOR_FRESHNESS, f"Newest snapshot is {freshness_hours:.1f}h old")
    return deny(
        MONITOR_FRESHNESS,
        f"Snapshot is fresh ({freshness_hours:.1f}h old) - a crawl would be redundant.",
        "data_freshness_hours",
    )


def check_monitor_hours(subject: Subject, *, now: datetime | None = None) -> Decision:
    """Monitoring passes are a weekday, 07:00-22:00 action."""
    if subject.role == ADMIN_ROLE:
        return allow(MONITOR_HOURS, "Admin may run outside business hours")
    stamp = now or datetime.now()
    if stamp.weekday() >= WEEKEND:
        return deny(
            MONITOR_HOURS,
            "Monitoring passes run on weekdays only (Mon-Fri).",
            "weekday",
        )
    current = stamp.time()
    if not BUSINESS_START <= current <= BUSINESS_END:
        return deny(
            MONITOR_HOURS,
            f"Monitoring passes run 07:00-22:00 server time (now {current.strftime('%H:%M')}).",
            "business_hours",
        )
    return allow(MONITOR_HOURS, "Inside the business-hours window")


def first_denial(*decisions: Decision) -> Decision | None:
    """The first failing decision, so a router can chain gates compactly."""
    for decision in decisions:
        if not decision.allowed:
            return decision
    return None
