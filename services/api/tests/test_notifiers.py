"""Alert delivery (notifier) tests - no live network except respx-mocked webhook."""

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx
from app.config import Settings
from app.db import AlertRecord, Base, SessionLocal, engine
from app.notifiers import build_notifiers
from app.notifiers.base import Notification, severity_at_least
from app.notifiers.webhook import WebhookNotifier
from app.schemas import Alert
from app.services import alerts


@pytest.fixture()
def session():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _settings(**overrides) -> Settings:
    base = dict(
        alert_notify_enabled=True,
        alert_notify_channels="console",
        alert_notify_min_severity="info",
        alert_notify_cooldown_minutes=360,
    )
    base.update(overrides)
    return Settings(**base)


def _alert(id: str, severity: str = "warning", slug: str = "p") -> Alert:
    return Alert(
        id=id,
        slug=slug,
        protocol="P One",
        rule="tvl_drop",
        severity=severity,
        message="TVL fell 20% over 7d",
        evidence={"metric": "tvl_change_7d_pct", "observed": -20.0, "threshold": -15.0},
        triggered_at=datetime.now(UTC).isoformat(),
    )


class Recorder:
    """Fake notifier that just remembers what it was asked to send."""

    name = "recorder"

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    async def send(self, http, note: Notification) -> None:
        self.sent.append(note)


class Boom:
    """Notifier that always fails - used to prove one channel can't abort a pass."""

    name = "boom"

    async def send(self, http, note: Notification) -> None:
        raise RuntimeError("endpoint down")


# --- severity ordering ------------------------------------------------------


def test_severity_ranking():
    assert severity_at_least("critical", "warning")
    assert severity_at_least("warning", "warning")
    assert not severity_at_least("info", "warning")
    # unknown severities are treated as the floor (info)
    assert not severity_at_least("mystery", "warning")


# --- notification content ---------------------------------------------------


def test_notification_renders_text_and_dict():
    note = Notification.from_alert(_alert("alert-x", severity="critical"))
    assert note.as_text() == "[CRITICAL] P One: TVL fell 20% over 7d"
    d = note.as_dict()
    assert d["id"] == "alert-x"
    assert d["severity"] == "critical"
    assert d["evidence"]["observed"] == -20.0


# --- dispatch: send, dedup, cooldown ---------------------------------------


async def test_notifies_new_alert_once_then_cooldown(session, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(alerts, "build_notifiers", lambda s: [rec])
    a = _alert("alert-aaa")
    alerts.persist_alerts(session, [a])
    settings = _settings()

    assert await alerts.notify_new_alerts(session, [a], http=None, settings=settings) == 1
    assert len(rec.sent) == 1

    # Same-day re-run within cooldown: nothing new is dispatched.
    assert await alerts.notify_new_alerts(session, [a], http=None, settings=settings) == 0
    assert len(rec.sent) == 1
    assert session.get(AlertRecord, "alert-aaa").notified_at is not None


async def test_resends_after_cooldown_elapses(session, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(alerts, "build_notifiers", lambda s: [rec])
    a = _alert("alert-bbb")
    alerts.persist_alerts(session, [a])
    settings = _settings(alert_notify_cooldown_minutes=0)

    assert await alerts.notify_new_alerts(session, [a], http=None, settings=settings) == 1
    assert await alerts.notify_new_alerts(session, [a], http=None, settings=settings) == 1
    assert len(rec.sent) == 2


async def test_below_min_severity_is_skipped(session, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(alerts, "build_notifiers", lambda s: [rec])
    a = _alert("alert-ccc", severity="info")
    alerts.persist_alerts(session, [a])
    settings = _settings(alert_notify_min_severity="warning")

    assert await alerts.notify_new_alerts(session, [a], http=None, settings=settings) == 0
    assert rec.sent == []
    # not marked notified - it can still be delivered if the gate is later lowered
    assert session.get(AlertRecord, "alert-ccc").notified_at is None


async def test_disabled_sends_nothing(session, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(alerts, "build_notifiers", lambda s: [rec])
    a = _alert("alert-ddd")
    alerts.persist_alerts(session, [a])
    settings = _settings(alert_notify_enabled=False)

    assert await alerts.notify_new_alerts(session, [a], http=None, settings=settings) == 0
    assert rec.sent == []


async def test_no_configured_notifiers_does_not_mark(session, monkeypatch):
    # webhook requested but no URL -> build_notifiers returns [] -> nothing sent,
    # nothing marked (so a later-configured channel can still deliver).
    a = _alert("alert-nochan")
    alerts.persist_alerts(session, [a])
    settings = _settings(alert_notify_channels="webhook")  # no url

    assert await alerts.notify_new_alerts(session, [a], http=None, settings=settings) == 0
    assert session.get(AlertRecord, "alert-nochan").notified_at is None


async def test_failing_channel_does_not_abort_pass(session, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(alerts, "build_notifiers", lambda s: [Boom(), rec])
    a = _alert("alert-eee")
    alerts.persist_alerts(session, [a])
    settings = _settings()

    assert await alerts.notify_new_alerts(session, [a], http=None, settings=settings) == 1
    # the healthy channel still received the alert despite the boom channel
    assert len(rec.sent) == 1
    assert session.get(AlertRecord, "alert-eee").notified_at is not None


# --- registry: build_notifiers ---------------------------------------------


def test_console_always_built_webhook_skipped_without_url():
    ns = build_notifiers(_settings(alert_notify_channels="console,webhook"))
    names = {n.name for n in ns}
    assert names == {"console"}


def test_webhook_built_when_url_configured():
    ns = build_notifiers(
        _settings(
            alert_notify_channels="console,webhook",
            alert_notify_webhook_url="https://hooks.example/x",
        )
    )
    assert {n.name for n in ns} == {"console", "webhook"}


def test_unconfigured_providers_are_skipped():
    ns = build_notifiers(_settings(alert_notify_channels="console,slack,discord,telegram,email"))
    # only console has no required config; the rest are dormant without secrets
    assert {n.name for n in ns} == {"console"}


def test_slack_built_when_webhook_url_set():
    ns = build_notifiers(
        _settings(alert_notify_channels="slack", slack_webhook_url="https://hooks.slack.com/T")
    )
    assert {n.name for n in ns} == {"slack"}


# --- webhook transport (respx-mocked) --------------------------------------


@respx.mock
async def test_webhook_generic_posts_full_json():
    route = respx.post("https://hooks.test/x").respond(200)
    note = Notification.from_alert(_alert("alert-fff"))
    async with httpx.AsyncClient() as http:
        await WebhookNotifier("https://hooks.test/x", "generic").send(http, note)
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body["id"] == "alert-fff"
    assert body["severity"] == "warning"
    assert body["message"] == "TVL fell 20% over 7d"


@respx.mock
async def test_webhook_slack_format_wraps_text():
    route = respx.post("https://hooks.slack.test/T").respond(200)
    note = Notification.from_alert(_alert("alert-ggg", severity="critical"))
    async with httpx.AsyncClient() as http:
        await WebhookNotifier("https://hooks.slack.test/T", "slack").send(http, note)
    body = json.loads(route.calls.last.request.content)
    assert body == {"text": "[CRITICAL] P One: TVL fell 20% over 7d"}
