"""Date/time helpers for user-facing Waybar output."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def format_reset(dt: datetime | None) -> str:
    if not dt:
        return "unknown"
    local_dt = dt.astimezone()
    seconds = int((dt - utc_now()).total_seconds())
    if seconds <= 0:
        rel = "now"
    else:
        minutes = seconds // 60
        hours, mins = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if days:
            rel = f"in {days}d {hours}h"
        elif hours:
            rel = f"in {hours}h {mins}m"
        else:
            rel = f"in {mins}m"
    return f"{rel} ({local_dt.strftime('%a %H:%M %Z')})"
