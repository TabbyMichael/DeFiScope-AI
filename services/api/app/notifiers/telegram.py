"""Telegram Bot API channel (env-backed; dormant unless configured).

The bot token is embedded in the request URL, so it must never be logged; on
failure we raise and the caller logs only the notifier *name*, never the URL.
"""

from __future__ import annotations

import httpx

from app.notifiers.base import Notification


class TelegramNotifier:
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, http: httpx.AsyncClient, note: Notification) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        resp = await http.post(url, json={"chat_id": self.chat_id, "text": note.as_text()})
        resp.raise_for_status()
