"""Helpers for normalized, privacy-safe pieces of Codex usage payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import Window
from .timefmt import parse_dt


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _window_detail(raw: Mapping[str, Any]) -> str | None:
    minutes = _float_or_none(raw.get("window_minutes"))
    if minutes and minutes > 0:
        return f"{int(minutes) if minutes.is_integer() else minutes:g}m window"

    seconds = _float_or_none(raw.get("limit_window_seconds"))
    if seconds and seconds > 0:
        if seconds % 3600 == 0:
            hours = seconds / 3600
            return f"{int(hours) if hours.is_integer() else hours:g}h window"
        if seconds % 60 == 0:
            mins = seconds / 60
            return f"{int(mins) if mins.is_integer() else mins:g}m window"
        return f"{int(seconds) if seconds.is_integer() else seconds:g}s window"

    return None


def _additional_limit_items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    containers = [payload, _mapping(payload.get("rate_limits"))]
    seen: set[int] = set()
    items: list[Mapping[str, Any]] = []
    for container in containers:
        if not container:
            continue
        for key in ("additional_rate_limits", "additional_limits"):
            raw_items = container.get(key)
            if isinstance(raw_items, Sequence) and not isinstance(raw_items, (str, bytes, bytearray)):
                for raw_item in raw_items:
                    item = _mapping(raw_item)
                    if item and id(item) not in seen:
                        seen.add(id(item))
                        items.append(item)
    return items


def _is_spark_limit(item: Mapping[str, Any]) -> bool:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("limit_name", "name", "label", "metered_feature", "limit_id")
    ).lower()
    return "spark" in text or "bengalfox" in text


def _extra_label(item: Mapping[str, Any]) -> str:
    # Current sanitized API shape exposes limit_name="GPT-5.3-Codex-Spark"
    # and metered_feature="codex_bengalfox". Keep the user-facing label short.
    if _is_spark_limit(item):
        return "Spark"
    raw = str(item.get("limit_name") or item.get("name") or item.get("label") or "Additional").strip()
    return raw.replace("_", " ").replace("-", " ").title() or "Additional"


def _window_from_rate_limit(raw: Mapping[str, Any], *, label: str) -> Window | None:
    used = _float_or_none(raw.get("used_percent"))
    reset_at = parse_dt(raw.get("reset_at", raw.get("resets_at")))
    detail = _window_detail(raw)
    if used is None and reset_at is None and detail is None:
        return None
    return Window(label=label, used_percent=used, reset_at=reset_at, detail=detail)


def spark_extra_windows_from_payload(payload: Mapping[str, Any]) -> tuple[Window, ...]:
    """Extract Spark-specific additional rate-limit windows.

    Sanitized live Codex account usage payloads expose Spark as an entry in
    ``additional_rate_limits`` with ``limit_name`` similar to
    ``GPT-5.3-Codex-Spark`` and ``metered_feature`` similar to
    ``codex_bengalfox``. Local token-count logs may expose the same list under
    ``payload.rate_limits`` if Codex decides to write it there. This helper only
    returns those additional Spark buckets; normal Codex session/weekly windows
    remain separate.
    """

    windows: list[Window] = []
    for item in _additional_limit_items(payload):
        if not _is_spark_limit(item):
            continue
        prefix = _extra_label(item)
        rate_limit = _mapping(item.get("rate_limit")) or item
        for key, suffix in (("primary_window", "Session"), ("primary", "Session"), ("secondary_window", "Weekly"), ("secondary", "Weekly")):
            window = _window_from_rate_limit(_mapping(rate_limit.get(key)), label=f"{prefix} {suffix}")
            if window is not None:
                windows.append(window)
    return tuple(windows)
