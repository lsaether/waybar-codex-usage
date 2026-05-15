"""Local Codex CLI session-log parser.

The parser intentionally extracts only token_count.rate_limits fields. Codex JSONL
files can contain prompts, code, paths, and other private content, so public tests
and issue reports should use sanitized fixtures rather than raw sessions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Usage, Window
from .timefmt import parse_dt


def _candidate_files(sessions_dir: Path, limit: int = 40) -> list[Path]:
    if sessions_dir.is_file() and sessions_dir.suffix == ".jsonl":
        return [sessions_dir]
    if not sessions_dir.exists():
        raise RuntimeError(f"No Codex session directory at {sessions_dir}")
    return sorted(sessions_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def _event_timestamp(event: dict[str, Any], path: Path) -> datetime:
    parsed = parse_dt(event.get("timestamp"))
    if parsed:
        return parsed
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def latest_local_rate_limit(sessions_dir: Path, *, file_limit: int = 40, max_scan_bytes: int = 160 * 1024 * 1024) -> Usage:
    """Return the newest local Codex token_count/rate_limits snapshot.

    Only fields under ``payload.rate_limits`` plus plan/timestamp are used.
    Prompt text and other message content are ignored.
    """

    latest_event: tuple[datetime, dict[str, Any]] | None = None
    scanned_bytes = 0

    for path in _candidate_files(Path(sessions_dir), file_limit):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if scanned_bytes >= max_scan_bytes:
            break
        scanned_bytes += size
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if '"token_count"' not in line or '"rate_limits"' not in line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    payload = event.get("payload") or {}
                    if event.get("type") != "event_msg" or payload.get("type") != "token_count":
                        continue
                    rate_limits = payload.get("rate_limits") or {}
                    if not rate_limits:
                        continue
                    ts = _event_timestamp(event, path)
                    if latest_event is None or ts > latest_event[0]:
                        latest_event = (ts, payload)
        except OSError:
            continue

    if latest_event is None:
        raise RuntimeError("No local Codex token_count/rate_limits event found")

    ts, payload = latest_event
    rate_limits = payload.get("rate_limits") or {}
    windows: list[Window] = []
    for key, label in (("primary", "Session"), ("secondary", "Weekly")):
        window = rate_limits.get(key) or {}
        if window.get("used_percent") is None:
            continue
        windows.append(
            Window(
                label=label,
                used_percent=float(window.get("used_percent")),
                reset_at=parse_dt(window.get("resets_at")),
                detail=(f"{window.get('window_minutes')}m window" if window.get("window_minutes") else None),
            )
        )

    if not windows:
        raise RuntimeError("Local Codex rate-limit event had no usable windows")

    plan = str(payload.get("plan_type") or "").strip().replace("_", " ").title() or None
    return Usage(
        provider="openai-codex",
        plan=plan,
        source="local Codex session log",
        fetched_at=ts,
        windows=tuple(windows),
        details=("Parsed newest local Codex CLI rate-limit snapshot.",),
        stale=True,
    )
