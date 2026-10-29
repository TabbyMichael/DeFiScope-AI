"""Slack incoming-webhook channel (env-backed; dormant unless configured)."""

from __future__ import annotations

import httpx

from app.notifiers.base import Notification


class SlackNotifier:
    name = "slack"

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def send(self, http: httpx.AsyncClient, note: Notification) -> None:
        resp = await http.post(self.webhook_url, json={"text": note.as_text()})
        resp.raise_for_status()
