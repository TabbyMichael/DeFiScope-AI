"""Generic webhook notifier - the second default channel.

POSTs JSON to ``alert_notify_webhook_url``. Only built when a URL is
configured, so the showcase stays silent until an endpoint is provided. The
``format`` selects the body shape: ``generic`` sends the full structured alert,
``slack``/``discord`` send the compatible minimal ``text``/``content`` envelope
so a raw incoming-webhook can be reused directly.
"""

from __future__ import annotations

import httpx

from app.notifiers.base import Notification


class WebhookNotifier:
    name = "webhook"

    def __init__(self, url: str, fmt: str = "generic") -> None:
        self.url = url
        self.fmt = fmt

    def _payload(self, note: Notification) -> dict:
        if self.fmt == "slack":
            return {"text": note.as_text()}
        if self.fmt == "discord":
            return {"content": note.as_text()}
        return note.as_dict()

    async def send(self, http: httpx.AsyncClient, note: Notification) -> None:
        resp = await http.post(self.url, json=self._payload(note))
        resp.raise_for_status()
