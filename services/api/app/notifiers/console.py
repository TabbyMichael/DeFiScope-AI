"""Console notifier - always safe, no external calls.

The default delivery channel for the no-secrets showcase: new alerts are
emitted to the application log so the monitoring pass is observable without
configuring any endpoint.
"""

from __future__ import annotations

import logging

import httpx

from app.notifiers.base import Notification

logger = logging.getLogger("defiscope.notify.console")


class ConsoleNotifier:
    name = "console"

    async def send(self, http: httpx.AsyncClient, note: Notification) -> None:
        logger.info("ALERT %s", note.as_text())
