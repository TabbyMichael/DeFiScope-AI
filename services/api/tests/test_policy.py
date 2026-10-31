"""The authorization matrix, tested as a pure function table.

No database, no HTTP client, no app: if a rule here needs infrastructure to
explain itself, the rule is in the wrong layer. Every assertion checks the
``policy`` id and (where it applies) the ``failed_predicate``, because a denial
that cannot name its own cause is not explainable.
"""

from datetime import datetime

import pytest
from app.schemas import Alert
from app.security import policy
from app.security.principal import ANONYMOUS, Subject
from app.security.rbac import (
    ALL_PERMISSIONS,
    AUDIT_READ,
    BRIEFS_EXPORT,
    BRIEFS_READ,
    CHAT_ASK,
    MONITOR_RUN,
    PROTOCOLS_READ,
    has_permission,
    permissions_for,
)

# --- subjects ---------------------------------------------------------------

VIEWER = Subject.from_values(user_id="u-viewer", email="viewer@demo", role="viewer", clearance=1)
ANALYST_SCOPED = Subject.from_values(
    user_id="u-analyst",
    email="analyst@demo",
    role="analyst",
    clearance=1,
    allowed_categories=["Lending", "Dexes"],
)
OFFICER = Subject.from_values(
    user_id="u-officer", email="officer@demo", role="risk_officer", clearance=2
)
ADMIN = Subject.from_values(user_id="u-admin", email="admin@demo", role="admin", clearance=3)

WEDNESDAY_NOON = datetime(2026, 3, 4, 12, 0)  # weekday()
SATURDAY_NOON = datetime(2026, 3, 7, 12, 0)


# --- RBAC -------------------------------------------------------------------


class TestRolePermissions:
    @pytest.mark.parametrize(
        ("role", "permission", "expected"),
        [
            ("viewer", PROTOCOLS_READ, True),
            ("viewer", CHAT_ASK, True),
            ("viewer", BRIEFS_EXPORT, False),
            ("viewer", MONITOR_RUN, False),
            ("analyst", PROTOCOLS_READ, True),
            ("analyst", BRIEFS_EXPORT, True),
            ("analyst", MONITOR_RUN, True),
            ("analyst", AUDIT_READ, False),
            ("risk_officer", AUDIT_READ, True),
            ("risk_officer", MONITOR_RUN, True),
            ("admin", AUDIT_READ, True),
            ("admin", "users:manage", True),
            # An unknown role is not a privileged one.
            ("intern", PROTOCOLS_READ, False),
            ("", PROTOCOLS_READ, False),
        ],
    )
    def test_role_matrix(self, role, permission, expected):
        subject = Subject.from_values(user_id="x", email="x@y", role=role)
        assert has_permission(subject, permission) is expected

    def test_every_role_is_read_capable_but_not_export_capable(self):
        # The distinction the whole layer exists for: seeing is not downloading.
        assert BRIEFS_READ in permissions_for("viewer")
        assert BRIEFS_EXPORT not in permissions_for("viewer")

    def test_admin_holds_every_verb(self):
        assert permissions_for("admin") == ALL_PERMISSIONS

    def test_synthetic_anonymous_principal_is_privileged(self):
        # Only ever served while auth_mode == "off"; asserted so its power is a
        # documented decision rather than an accident.
        assert has_permission(ANONYMOUS, MONITOR_RUN)
        assert ANONYMOUS.authenticated is False


class TestScopePolicy:
    def test_unrestricted_subject_may_read_anything(self):
        for category, chain in [("Lending", "Ethereum"), (None, None), ("CEX", "Tron")]:
            assert policy.check_scope(VIEWER, category=category, chain=chain).allowed

    def test_restricted_subject_is_allowed_inside_its_categories(self):
        decision = policy.check_scope(ANALYST_SCOPED, category="Lending", chain="Ethereum")
        assert decision.allowed and decision.policy == policy.SCOPE

    def test_restricted_subject_is_denied_outside_its_categories(self):
        decision = policy.check_scope(ANALYST_SCOPED, category="Derivatives", chain="Ethereum")
        assert not decision.allowed
        assert decision.failed_predicate == "category"
        # The reason names what the caller *does* cover, so it is actionable.
        assert "Lending" in decision.reason and "Derivatives" in decision.reason

    def test_unknown_category_is_denied_not_defaulted_to_allowed(self):
        decision = policy.check_scope(ANALYST_SCOPED, category=None, chain=None)
        assert not decision.allowed
        assert decision.failed_predicate == "category"
        assert "no category" in decision.reason

    def test_chain_axis_is_enforced_independently(self):
        subject = Subject.from_values(
            user_id="u", email="u@d", role="analyst", allowed_chains=["Ethereum"]
        )
        assert policy.check_scope(subject, category="Derivatives", chain="Ethereum").allowed
        decision = policy.check_scope(subject, category="Lending", chain="Solana")
        assert not decision.allowed
        assert decision.failed_predicate == "top_chain"

    def test_wildcard_means_unrestricted(self):
        subject = Subject.from_values(
            user_id="u",
            email="u@d",
            role="analyst",
            allowed_categories=["*"],
            allowed_chains=["*"],
        )
        assert subject.scope.restricted is False
        assert policy.check_scope(subject, category="Anything", chain="Anywhere").allowed

    def test_denial_serialises_for_an_http_body(self):
        detail = policy.check_scope(ANALYST_SCOPED, category="CEX", chain="Ethereum").as_detail()
        assert detail["error"] == "forbidden"
        assert detail["policy"] == policy.SCOPE
        assert detail["failed_predicate"] == "category"
        assert detail["reason"]


# --- alerts.severity_clearance ---------------------------------------------


def _alert(severity: str, slug: str = "aave-v3", n: int = 0) -> Alert:
    return Alert(
        id=f"alert-{slug}-{severity}-{n}",
        slug=slug,
        protocol=slug,
        rule="daily_shock",
        severity=severity,
        message=f"{severity} event",
        evidence={},
        triggered_at="2026-03-04T00:00:00+00:00",
    )


class TestAlertClearance:
    def test_clearance_one_cannot_read_critical(self):
        decision = policy.check_alert_visibility(VIEWER, severity="critical")
        assert not decision.allowed
        assert decision.policy == policy.ALERT_CLEARANCE
        assert decision.failed_predicate == "clearance"
        assert "clearance 2" in decision.reason

    def test_clearance_two_can(self):
        assert policy.check_alert_visibility(OFFICER, severity="critical").allowed

    @pytest.mark.parametrize("severity", ["info", "warning"])
    def test_non_critical_alerts_are_not_gated(self, severity):
        assert policy.check_alert_visibility(VIEWER, severity=severity).allowed

    def test_withheld_alerts_are_counted_not_dropped(self):
        alerts = [
            _alert("critical", n=1),
            _alert("critical", n=2),
            _alert("warning", n=3),
        ]
        visible, withheld = policy.split_visible_alerts(alerts, VIEWER)
        assert withheld == 2
        assert [a.severity for a in visible] == ["warning"]

    def test_out_of_scope_alerts_are_neither_shown_nor_counted(self):
        alerts = [
            _alert("critical", slug="in-scope", n=1),
            _alert("critical", slug="other-desk", n=2),
        ]
        visible, withheld = policy.split_visible_alerts(alerts, VIEWER, visible_slugs={"in-scope"})
        # The second alert is not withheld *from this reader*: it is not theirs.
        assert withheld == 1
        assert [a.slug for a in visible] == []


# --- briefs.export.confidence_gate -----------------------------------------


class TestBriefExportGate:
    def test_low_confidence_blocks_an_analyst_and_names_the_gaps(self):
        decision = policy.check_brief_export(
            ANALYST_SCOPED, confidence="low", data_gaps=["a", "b", "c"]
        )
        assert not decision.allowed
        assert decision.policy == policy.BRIEF_CONFIDENCE
        assert decision.failed_predicate == "confidence"
        assert "3 data gaps" in decision.reason

    @pytest.mark.parametrize("role_subject", [OFFICER, ADMIN])
    def test_sign_off_roles_may_export_low_confidence(self, role_subject):
        assert policy.check_brief_export(role_subject, confidence="low", data_gaps=["a"]).allowed

    @pytest.mark.parametrize("confidence", ["high", "medium"])
    def test_confident_briefs_are_not_gated(self, confidence):
        assert policy.check_brief_export(VIEWER, confidence=confidence).allowed


# --- monitor.run.freshness / business_hours --------------------------------


class TestMonitorGates:
    def test_fresh_snapshot_blocks_a_redundant_crawl(self):
        decision = policy.check_monitor_freshness(ANALYST_SCOPED, freshness_hours=0.5)
        assert not decision.allowed
        assert decision.policy == policy.MONITOR_FRESHNESS
        assert decision.failed_predicate == "data_freshness_hours"
        assert "redundant" in decision.reason

    def test_stale_snapshot_permits_a_crawl(self):
        assert policy.check_monitor_freshness(ANALYST_SCOPED, freshness_hours=7.5).allowed

    def test_never_captured_permits_a_crawl(self):
        assert policy.check_monitor_freshness(ANALYST_SCOPED, freshness_hours=None).allowed

    def test_admin_may_force_a_pass_on_fresh_data(self):
        assert policy.check_monitor_freshness(ADMIN, freshness_hours=0.1).allowed

    def test_default_threshold_matches_the_dashboard_staleness_window(self):
        from app.services.dashboard import STALE_AFTER

        hours = STALE_AFTER.total_seconds() / 3600
        assert (
            policy.check_monitor_freshness(ANALYST_SCOPED, freshness_hours=hours - 0.1).allowed
            is False
        )
        assert (
            policy.check_monitor_freshness(ANALYST_SCOPED, freshness_hours=hours + 0.1).allowed
            is True
        )

    def test_inside_business_hours_is_allowed(self):
        assert policy.check_monitor_hours(ANALYST_SCOPED, now=WEDNESDAY_NOON).allowed

    def test_outside_business_hours_is_refused_with_the_window(self):
        decision = policy.check_monitor_hours(ANALYST_SCOPED, now=datetime(2026, 3, 4, 23, 30))
        assert not decision.allowed
        assert decision.failed_predicate == "business_hours"
        assert "07:00-22:00" in decision.reason

    def test_weekend_is_refused(self):
        decision = policy.check_monitor_hours(ANALYST_SCOPED, now=SATURDAY_NOON)
        assert not decision.allowed
        assert decision.failed_predicate == "weekday"

    def test_admin_bypasses_the_window(self):
        assert policy.check_monitor_hours(ADMIN, now=SATURDAY_NOON).allowed


class TestFirstDenial:
    def test_returns_the_first_failing_decision(self):
        allowed = policy.allow("x", "ok")
        denied = policy.deny("y", "no", "attr")
        assert policy.first_denial(allowed, denied) is denied
        assert policy.first_denial(allowed, allowed) is None
