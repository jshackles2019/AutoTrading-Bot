"""Notification helpers for external alert channels (Discord webhook)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional
from urllib import request


DEFAULT_EVENTS = {
    "circuit_halt",
    "fatal_error",
    "preflight_block",
    "reconciliation_mismatch",
    "schedule_block",
    "session_summary",
    "watchdog_restart",
    "watchdog_stop",
}


def _enabled_events() -> set[str]:
    raw = os.getenv("DISCORD_NOTIFY_EVENTS", "").strip()
    if not raw:
        return set(DEFAULT_EVENTS)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def notify_discord(event: str, message: str, title: Optional[str] = None) -> bool:
    """Send a plain Discord webhook notification for selected events.

    Environment:
    - DISCORD_WEBHOOK_URL: Discord incoming webhook URL
    - DISCORD_NOTIFY_EVENTS: comma-separated event names (optional)
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False

    event_key = (event or "").strip().lower()
    if not event_key or event_key not in _enabled_events():
        return False

    subject = title or f"Breakout Bot | {event_key}"
    content = f"**{subject}**\n{message}\n`{datetime.now().isoformat(timespec='seconds')}`"
    payload = {"content": content[:1900]}
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=5) as resp:
            return 200 <= int(resp.status) < 300
    except Exception:
        return False
