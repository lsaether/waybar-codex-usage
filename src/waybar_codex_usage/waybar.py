"""Render normalized Codex usage as Waybar custom-module JSON."""

from __future__ import annotations

from typing import Any

from .models import Usage, Window
from .timefmt import format_reset


def format_pct(value: float | None) -> str:
    if value is None:
        return "--%"
    value = max(0.0, min(999.0, float(value)))
    if abs(value - round(value)) < 0.05:
        return f"{int(round(value))}%"
    return f"{value:.1f}%"


def label_window(windows: tuple[Window, ...], *needles: str) -> Window | None:
    for needle in needles:
        for window in windows:
            if needle in window.label.lower():
                return window
    return None


def waybar_class(usage: Usage) -> str:
    if usage.error:
        return "error"
    if usage.stale:
        return "stale"
    used_values = [w.used_percent for w in usage.windows if w.used_percent is not None]
    high = max(used_values or [0.0])
    if high >= 95:
        return "critical"
    if high >= 80:
        return "warning"
    return "ok"


def usage_to_waybar(usage: Usage) -> dict[str, Any]:
    session = label_window(usage.windows, "session", "primary", "current")
    weekly = label_window(usage.windows, "weekly", "week", "secondary")

    if session and weekly:
        text = f"CX {format_pct(session.used_percent)} W{format_pct(weekly.used_percent)}"
    elif session:
        text = f"CX {format_pct(session.used_percent)}"
    elif weekly:
        text = f"CX W{format_pct(weekly.used_percent)}"
    else:
        text = "CX --"

    title = "Codex usage"
    if usage.plan:
        title += f" · {usage.plan}"
    lines = [title]
    for window in (*usage.windows, *usage.extra_windows):
        if window.used_percent is None:
            base = f"{window.label}: unavailable"
        else:
            remaining = max(0, round(100.0 - float(window.used_percent)))
            used = round(float(window.used_percent), 1)
            base = f"{window.label}: {remaining}% remaining ({used:g}% used)"
        if window.reset_at:
            base += f" · resets {format_reset(window.reset_at)}"
        elif window.detail:
            base += f" · {window.detail}"
        lines.append(base)
    lines.extend(usage.details)
    if usage.stale:
        lines.append("Showing cached/local fallback data")
    if usage.error:
        lines.append(f"Error: {usage.error}")
    lines.append(f"Updated: {usage.fetched_at.astimezone().strftime('%a %H:%M:%S %Z')}")
    lines.append(f"Source: {usage.source}")
    lines.append("Click to refresh")

    percentages = [w.used_percent for w in usage.windows if w.used_percent is not None]
    return {
        "text": text,
        "tooltip": "\n".join(lines),
        "class": waybar_class(usage),
        "percentage": int(round(max(percentages or [0.0]))),
        "alt": "codex",
    }
