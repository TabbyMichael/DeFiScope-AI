"""Email (SMTP) channel (env-backed; dormant unless configured).

``smtplib`` is blocking, so the synchronous send runs in a worker thread to
keep the async monitoring loop responsive. Password/credentials are used only
to open the connection and are never logged or persisted.
"""

from __future__ import annotations

import asyncio
import json
import smtplib
from email.message import EmailMessage

import httpx

from app.notifiers.base import Notification


class EmailNotifier:
    name = "email"

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        recipient: str,
        username: str | None = None,
        password: str | None = None,
        starttls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.sender = sender
        self.recipient = recipient
        self.username = username
        self.password = password
        self.starttls = starttls

    def _send_sync(self, note: Notification) -> None:
        msg = EmailMessage()
        msg["Subject"] = f"DeFiScope alert [{note.severity}]: {note.protocol}"
        msg["From"] = self.sender
        msg["To"] = self.recipient
        msg.set_content(
            f"{note.message}\n\nProtocol slug: {note.slug}\nRule: {note.rule}\n"
            f"Triggered: {note.triggered_at}\n\nEvidence:\n{json.dumps(note.evidence, indent=2)}"
        )
        with smtplib.SMTP(self.host, self.port, timeout=30) as server:
            if self.starttls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.send_message(msg)

    async def send(self, http: httpx.AsyncClient, note: Notification) -> None:
        await asyncio.to_thread(self._send_sync, note)
