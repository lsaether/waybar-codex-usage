"""Optional Hermes Agent integration.

This backend is intentionally optional: the published package should remain a
small standard-library Waybar module, while Hermes users can opt into the same
account-usage helper used by their agent installation.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from .codex_payload import spark_extra_windows_from_payload
from .models import Usage, Window
from .timefmt import parse_dt, utc_now


_HELPER_CODE = r'''
from __future__ import annotations

import json
import os
import pathlib
import sys

repo = pathlib.Path(os.environ["WAYBAR_CODEX_HERMES_REPO"])
if str(repo) not in sys.path:
    sys.path.insert(0, str(repo))

from agent.account_usage import fetch_account_usage  # type: ignore

snapshot = fetch_account_usage("openai-codex")
if not snapshot or not getattr(snapshot, "available", False):
    raise RuntimeError("Codex usage API returned no usable account window")


def clean_dt(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

payload = {
    "available": bool(getattr(snapshot, "available", False)),
    "provider": str(getattr(snapshot, "provider", "openai-codex") or "openai-codex"),
    "plan": (str(getattr(snapshot, "plan", "") or "").strip() or None),
    "details": [str(x) for x in getattr(snapshot, "details", ()) if x],
    "windows": [
        {
            "label": str(getattr(raw, "label", "Window") or "Window"),
            "used_percent": getattr(raw, "used_percent", None),
            "reset_at": clean_dt(getattr(raw, "reset_at", None)),
            "detail": getattr(raw, "detail", None),
        }
        for raw in getattr(snapshot, "windows", ())
    ],
    "extra_windows": [
        {
            "label": str(getattr(raw, "label", "Window") or "Window"),
            "used_percent": getattr(raw, "used_percent", None),
            "reset_at": clean_dt(getattr(raw, "reset_at", None)),
            "detail": getattr(raw, "detail", None),
        }
        for raw in getattr(snapshot, "extra_windows", ())
    ],
}


def _resolve_codex_usage_url(base_url):
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        normalized = "https://chatgpt.com/backend-api/codex"
    if normalized.endswith("/codex"):
        normalized = normalized[: -len("/codex")]
    if "/backend-api" in normalized:
        return normalized + "/wham/usage"
    return normalized + "/api/codex/usage"


def _spark_extra_windows_from_usage_payload(raw_payload):
    items = []
    for container in (raw_payload, (raw_payload.get("rate_limits") or {})):
        if not isinstance(container, dict):
            continue
        raw_items = container.get("additional_rate_limits") or container.get("additional_limits") or []
        if isinstance(raw_items, list):
            items.extend(x for x in raw_items if isinstance(x, dict))

    windows = []
    for item in items:
        searchable = " ".join(str(item.get(key) or "") for key in ("limit_name", "name", "label", "metered_feature", "limit_id")).lower()
        if "spark" not in searchable and "bengalfox" not in searchable:
            continue
        rate_limit = item.get("rate_limit") if isinstance(item.get("rate_limit"), dict) else item
        for key, suffix in (("primary_window", "Session"), ("primary", "Session"), ("secondary_window", "Weekly"), ("secondary", "Weekly")):
            raw_window = rate_limit.get(key) if isinstance(rate_limit, dict) else None
            if not isinstance(raw_window, dict):
                continue
            used = raw_window.get("used_percent")
            reset = raw_window.get("reset_at", raw_window.get("resets_at"))
            if used is None and reset is None:
                continue
            windows.append({
                "label": f"Spark {suffix}",
                "used_percent": used,
                "reset_at": clean_dt(reset),
                "detail": None,
            })
    return windows


def _fetch_live_spark_extra_windows():
    try:
        import httpx
        from hermes_cli.auth import _read_codex_tokens, resolve_codex_runtime_credentials

        creds = resolve_codex_runtime_credentials(refresh_if_expiring=True)
        token_data = _read_codex_tokens()
        tokens = token_data.get("tokens") or {}
        account_id = str(tokens.get("account_id", "") or "").strip() or None
        headers = {
            "Authorization": f"Bearer {creds['api_key']}",
            "Accept": "application/json",
            "User-Agent": "codex-cli",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id
        with httpx.Client(timeout=float(os.environ.get("WAYBAR_CODEX_HERMES_TIMEOUT", "25"))) as client:
            response = client.get(_resolve_codex_usage_url(str(creds.get("base_url", ""))), headers=headers)
            response.raise_for_status()
        return _spark_extra_windows_from_usage_payload(response.json() or {})
    except Exception:
        return []


if not payload["extra_windows"]:
    payload["extra_windows"] = _fetch_live_spark_extra_windows()

print(json.dumps(payload, ensure_ascii=False))
'''


_SECRET_PATTERNS = (
    re.compile("Bear" + r"er\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE),
    re.compile("s" + r"k-[A-Za-z0-9_-]+"),
    re.compile("github" + r"_pat_[A-Za-z0-9_]+"),
    re.compile("gh" + r"[opsu]_[A-Za-z0-9_]+"),
)


def _brief_error(error: BaseException | str) -> str:
    text = str(error).strip().replace("\n", "; ")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    if len(text) > 500:
        text = text[:497] + "..."
    if text:
        return text
    if isinstance(error, BaseException):
        return error.__class__.__name__
    return "unknown error"


def _resolve_repo(hermes_repo: Path | None = None) -> Path:
    return Path(hermes_repo or os.environ.get("HERMES_AGENT_REPO", Path.home() / ".hermes" / "hermes-agent"))


def _resolve_hermes_python(repo: Path) -> Path | None:
    candidates: list[Path] = []
    if os.environ.get("HERMES_AGENT_PYTHON"):
        candidates.append(Path(os.environ["HERMES_AGENT_PYTHON"]))
    candidates.extend(
        (
            repo / "venv" / "bin" / "python3",
            repo / "venv" / "bin" / "python",
            repo / ".venv" / "bin" / "python3",
            repo / ".venv" / "bin" / "python",
        )
    )
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def _resolve_codex_usage_url(base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        normalized = "https://chatgpt.com/backend-api/codex"
    if normalized.endswith("/codex"):
        normalized = normalized[: -len("/codex")]
    if "/backend-api" in normalized:
        return normalized + "/wham/usage"
    return normalized + "/api/codex/usage"


def _fetch_live_spark_windows_via_hermes_auth() -> tuple[Window, ...]:
    # Imported lazily so the package stays stdlib-only unless the optional
    # Hermes backend is selected and Hermes' own dependency environment is used.
    import httpx  # type: ignore
    from hermes_cli.auth import _read_codex_tokens, resolve_codex_runtime_credentials  # type: ignore

    creds = resolve_codex_runtime_credentials(refresh_if_expiring=True)
    token_data = _read_codex_tokens()
    tokens = token_data.get("tokens") or {}
    account_id = str(tokens.get("account_id", "") or "").strip() or None
    headers = {
        "Authorization": f"Bearer {creds['api_key']}",
        "Accept": "application/json",
        "User-Agent": "codex-cli",
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    with httpx.Client(timeout=float(os.environ.get("WAYBAR_CODEX_HERMES_TIMEOUT", "25"))) as client:
        response = client.get(_resolve_codex_usage_url(str(creds.get("base_url", ""))), headers=headers)
        response.raise_for_status()
    return spark_extra_windows_from_payload(response.json() or {})


def _with_live_spark_windows(usage: Usage) -> Usage:
    if usage.extra_windows:
        return usage
    try:
        extra_windows = _fetch_live_spark_windows_via_hermes_auth()
    except Exception:
        return usage
    if not extra_windows:
        return usage
    return replace(usage, extra_windows=extra_windows)


def _windows_from_mapping(data: dict[str, Any], key: str) -> tuple[Window, ...]:
    windows_list: list[Window] = []
    for raw in data.get(key, ()):
        if not isinstance(raw, dict):
            continue
        used_raw = raw.get("used_percent")
        windows_list.append(
            Window(
                label=str(raw.get("label") or "Window"),
                used_percent=(None if used_raw is None else float(used_raw)),
                reset_at=parse_dt(raw.get("reset_at")),
                detail=(None if raw.get("detail") is None else str(raw.get("detail"))),
            )
        )
    return tuple(windows_list)


def _usage_from_mapping(data: dict[str, Any], *, source: str) -> Usage:
    if not data or not data.get("available", False):
        raise RuntimeError("Codex usage API returned no usable account window")

    windows = _windows_from_mapping(data, "windows")
    extra_windows = _windows_from_mapping(data, "extra_windows")
    details = tuple(str(x) for x in data.get("details", ()) if x)
    return Usage(
        provider=str(data.get("provider") or "openai-codex"),
        plan=(str(data.get("plan") or "").strip() or None),
        source=source,
        fetched_at=utc_now(),
        windows=windows,
        details=details,
        extra_windows=extra_windows,
    )


def _windows_from_snapshot_attr(snapshot: Any, attr: str) -> tuple[Window, ...]:
    return tuple(
        Window(
            label=str(getattr(raw, "label", "Window") or "Window"),
            used_percent=(None if getattr(raw, "used_percent", None) is None else float(getattr(raw, "used_percent"))),
            reset_at=getattr(raw, "reset_at", None),
            detail=getattr(raw, "detail", None),
        )
        for raw in getattr(snapshot, attr, ())
    )


def _usage_from_snapshot(snapshot: Any, *, source: str) -> Usage:
    if not snapshot or not getattr(snapshot, "available", False):
        raise RuntimeError("Codex usage API returned no usable account window")

    windows = _windows_from_snapshot_attr(snapshot, "windows")
    extra_windows = _windows_from_snapshot_attr(snapshot, "extra_windows")
    details = tuple(str(x) for x in getattr(snapshot, "details", ()) if x)
    return Usage(
        provider=str(getattr(snapshot, "provider", "openai-codex") or "openai-codex"),
        plan=(str(getattr(snapshot, "plan", "") or "").strip() or None),
        source=source,
        fetched_at=utc_now(),
        windows=windows,
        details=details,
        extra_windows=extra_windows,
    )


def _fetch_in_current_process(repo: Path) -> Usage:
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from agent.account_usage import fetch_account_usage  # type: ignore

    snapshot = fetch_account_usage("openai-codex")
    return _with_live_spark_windows(_usage_from_snapshot(snapshot, source="Hermes OpenAI-Codex usage helper"))


def _fetch_with_hermes_python(repo: Path, python: Path) -> Usage:
    env = os.environ.copy()
    env["WAYBAR_CODEX_HERMES_REPO"] = str(repo)
    proc = subprocess.run(
        [str(python), "-c", _HELPER_CODE],
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=float(os.environ.get("WAYBAR_CODEX_HERMES_TIMEOUT", "25")),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Hermes Python exited {proc.returncode}: {_brief_error(proc.stderr or proc.stdout)}")

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("Hermes Python returned no usage payload")
    try:
        data = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Hermes Python returned invalid usage payload: {_brief_error(exc)}") from exc
    return _usage_from_mapping(data, source="Hermes OpenAI-Codex usage helper")


def fetch_via_hermes(hermes_repo: Path | None = None) -> Usage:
    repo = _resolve_repo(hermes_repo)
    if not repo.exists():
        raise RuntimeError(f"Hermes repo not found at {repo}")

    direct_error: Exception | None = None
    try:
        return _fetch_in_current_process(repo)
    except Exception as exc:
        direct_error = exc

    hermes_python = _resolve_hermes_python(repo)
    if hermes_python is not None:
        try:
            return _fetch_with_hermes_python(repo, hermes_python)
        except Exception as subprocess_error:
            raise RuntimeError(
                "Hermes backend failed in current Python "
                f"({_brief_error(direct_error)}) and Hermes Python "
                f"({_brief_error(subprocess_error)})"
            ) from subprocess_error

    raise RuntimeError(
        "Hermes backend failed in current Python "
        f"({_brief_error(direct_error)}) and no Hermes Python was found. "
        "Set HERMES_AGENT_PYTHON or install Hermes dependencies in this environment."
    ) from direct_error
