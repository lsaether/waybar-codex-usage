"""Small data model shared by Codex usage sources and renderers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Window:
    """A single usage/rate-limit window."""

    label: str
    used_percent: float | None = None
    reset_at: datetime | None = None
    detail: str | None = None


@dataclass(frozen=True)
class Usage:
    """Normalized usage snapshot."""

    provider: str
    plan: str | None
    source: str
    fetched_at: datetime
    windows: tuple[Window, ...]
    details: tuple[str, ...] = ()
    stale: bool = False
    error: str | None = None
    extra_windows: tuple[Window, ...] = ()
