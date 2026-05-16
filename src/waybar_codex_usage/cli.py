"""Command-line entry point for the Waybar Codex usage module."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Sequence

from .codex_api import default_codex_home, fetch_via_codex_api
from .codex_logs import latest_local_rate_limit
from .hermes_backend import fetch_via_hermes
from .models import Usage
from .timefmt import utc_now
from .waybar import usage_to_waybar


def default_cache_path() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return Path(os.environ.get("WAYBAR_CODEX_USAGE_CACHE", base / "waybar-codex-usage.json"))


def default_sessions_dir() -> Path:
    return Path(os.environ.get("CODEX_SESSIONS_DIR", Path.home() / ".codex" / "sessions"))


def cache_fresh(path: Path, ttl: int) -> bool:
    try:
        return path.exists() and (time.time() - path.stat().st_mtime) < ttl
    except OSError:
        return False


def read_cache(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def write_cache(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False) + "\n")
        tmp.replace(path)
    except Exception:
        # Waybar modules should prefer showing data over surfacing cache IO noise.
        pass


def error_payload(message: str, stale_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if stale_payload:
        payload = dict(stale_payload)
        classes = str(payload.get("class") or "").split()
        if "stale" not in classes:
            classes.append("stale")
        payload["class"] = " ".join(c for c in classes if c)
        tooltip = str(payload.get("tooltip") or "")
        payload["tooltip"] = (tooltip + "\n" if tooltip else "") + f"Refresh error: {message}"
        return payload

    usage = Usage(
        provider="openai-codex",
        plan=None,
        source="unavailable",
        fetched_at=utc_now(),
        windows=(),
        error=message,
    )
    return usage_to_waybar(usage)


def fetch_usage(source: str, sessions_dir: Path, hermes_repo: Path | None, codex_home: Path | None) -> Usage:
    if source in {"codex", "codex-api"}:
        return fetch_via_codex_api(codex_home=codex_home)
    if source == "logs":
        return latest_local_rate_limit(sessions_dir)
    if source == "hermes":
        return fetch_via_hermes(hermes_repo)
    if source == "auto":
        try:
            return fetch_via_codex_api(codex_home=codex_home)
        except Exception:
            pass
        try:
            return fetch_via_hermes(hermes_repo)
        except Exception:
            return latest_local_rate_limit(sessions_dir)
    raise ValueError(f"unknown source: {source}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emit Codex usage as Waybar custom-module JSON")
    parser.add_argument("--source", choices=("codex", "codex-api", "logs", "hermes", "auto"), default=os.environ.get("WAYBAR_CODEX_USAGE_SOURCE", "logs"), help="usage source (default: logs; auto tries codex, hermes, then logs)")
    parser.add_argument("--offline", action="store_true", help="legacy alias for --source logs; bypasses online/cache reads")
    parser.add_argument("--sessions-dir", type=Path, default=default_sessions_dir(), help="Codex session directory or a single JSONL file")
    parser.add_argument("--codex-home", type=Path, default=default_codex_home(), help="Codex home directory containing auth.json (default: CODEX_HOME or ~/.codex)")
    parser.add_argument("--hermes-repo", type=Path, default=None, help="optional Hermes Agent checkout for --source hermes/auto")
    parser.add_argument("--cache", type=Path, default=default_cache_path(), help="rendered Waybar payload cache path")
    parser.add_argument("--ttl", type=int, default=int(os.environ.get("WAYBAR_CODEX_USAGE_TTL", "300")), help="cache TTL in seconds")
    parser.add_argument("--refresh", action="store_true", help="ignore cache and fetch now")
    parser.add_argument("--plain", action="store_true", help="print compact text only")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on refresh failure instead of Waybar-friendly zero")
    return parser


def emit(payload: dict[str, Any], *, plain: bool) -> None:
    print(payload.get("text", "CX --") if plain else json.dumps(payload, ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source = "logs" if args.offline else args.source

    # Preserve the legacy local-widget meaning of --offline: do not call the
    # account API and do not reuse a cached online/API response.
    if not args.refresh and not args.offline and cache_fresh(args.cache, args.ttl):
        cached = read_cache(args.cache)
        if cached:
            emit(cached, plain=args.plain)
            return 0

    stale_cache = read_cache(args.cache)
    try:
        usage = fetch_usage(source, args.sessions_dir, args.hermes_repo, args.codex_home)
    except Exception as exc:
        payload = error_payload(str(exc), stale_cache)
        emit(payload, plain=args.plain)
        return 1 if args.strict else 0

    payload = usage_to_waybar(usage)
    write_cache(args.cache, payload)
    emit(payload, plain=args.plain)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
