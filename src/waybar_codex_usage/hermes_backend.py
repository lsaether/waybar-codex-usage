"""Optional Hermes Agent integration.

This backend is intentionally optional: the published package should remain a
small standard-library Waybar module, while Hermes users can opt into the same
account-usage helper used by their agent installation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .models import Usage, Window
from .timefmt import utc_now


def fetch_via_hermes(hermes_repo: Path | None = None) -> Usage:
    repo = Path(hermes_repo or os.environ.get("HERMES_AGENT_REPO", Path.home() / ".hermes" / "hermes-agent"))
    if not repo.exists():
        raise RuntimeError(f"Hermes repo not found at {repo}")
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from agent.account_usage import fetch_account_usage  # type: ignore

    snapshot = fetch_account_usage("openai-codex")
    if not snapshot or not getattr(snapshot, "available", False):
        raise RuntimeError("Codex usage API returned no usable account window")

    windows = tuple(
        Window(
            label=str(getattr(raw, "label", "Window") or "Window"),
            used_percent=(None if getattr(raw, "used_percent", None) is None else float(getattr(raw, "used_percent"))),
            reset_at=getattr(raw, "reset_at", None),
            detail=getattr(raw, "detail", None),
        )
        for raw in getattr(snapshot, "windows", ())
    )
    details = tuple(str(x) for x in getattr(snapshot, "details", ()) if x)
    return Usage(
        provider=str(getattr(snapshot, "provider", "openai-codex") or "openai-codex"),
        plan=(str(getattr(snapshot, "plan", "") or "").strip() or None),
        source="Hermes OpenAI-Codex usage helper",
        fetched_at=utc_now(),
        windows=windows,
        details=details,
    )
