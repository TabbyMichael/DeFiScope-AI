"""Alert delivery channels, assembled from settings.

``build_notifiers`` turns ``alert_notify_channels`` into concrete notifier
instances, skipping any channel whose required env-backed config is absent.
This keeps the showcase runnable with zero secrets (``console`` always works,
``webhook`` activates only once a URL is set) while letting an operator opt into
Slack/Discord/Telegram/email purely through the environment.
"""

from __future__ import annotations

import logging

from app.config import Settings
from app.notifiers.base import Notification, Notifier, severity_at_least
from app.notifiers.console import ConsoleNotifier
from app.notifiers.discord import DiscordNotifier
from app.notifiers.email import EmailNotifier
from app.notifiers.slack import SlackNotifier
from app.notifiers.telegram import TelegramNotifier
from app.notifiers.webhook import WebhookNotifier

logger = logging.getLogger(__name__)

__all__ = [
    "Notification",
    "Notifier",
    "severity_at_least",
    "build_notifiers",
]


def _build_one(channel: str, s: Settings) -> Notifier | None:
    """Instantiate one requested channel, or ``None`` if it is not configured."""
    if channel == "console":
        return ConsoleNotifier()
    if channel == "webhook":
        if s.alert_notify_webhook_url:
            return WebhookNotifier(s.alert_notify_webhook_url, s.alert_notify_webhook_format)
        return None
    if channel == "slack":
        return SlackNotifier(s.slack_webhook_url) if s.slack_webhook_url else None
    if channel == "discord":
        return DiscordNotifier(s.discord_webhook_url) if s.discord_webhook_url else None
    if channel == "telegram":
        if s.telegram_bot_token and s.telegram_chat_id:
            return TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id)
        return None
    if channel == "email":
        if s.smtp_host and s.smtp_from and s.smtp_to:
            return EmailNotifier(
                host=s.smtp_host,
                port=s.smtp_port,
                sender=s.smtp_from,
                recipient=s.smtp_to,
                username=s.smtp_username,
                password=s.smtp_password,
                starttls=s.smtp_starttls,
            )
        return None
    logger.warning("Unknown alert notify channel %r - ignoring", channel)
    return None


def build_notifiers(s: Settings) -> list[Notifier]:
    notifiers: list[Notifier] = []
    for channel in s.notify_channel_list:
        instance = _build_one(channel, s)
        if instance is None:
            if channel != "console":
                logger.info("Notify channel %r requested but not configured - skipping", channel)
            continue
        notifiers.append(instance)
    return notifiers
