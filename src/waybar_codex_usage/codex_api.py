"""First-class Codex/ChatGPT usage API backend."""

from __future__ import annotations

import base64
import json
import os
import stat
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .codex_payload import spark_extra_windows_from_payload
from .models import Usage, Window
from .timefmt import parse_dt, utc_now

DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120
DEFAULT_TIMEOUT_SECONDS = 15.0


class _Response(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...
    def raise_for_status(self) -> None: ...


class _Client(Protocol):
    def __enter__(self) -> "_Client": ...
    def __exit__(self, *exc: object) -> object: ...
    def get(self, url: str, *, headers: Mapping[str, str]) -> _Response: ...
    def post(self, url: str, *, headers: Mapping[str, str] | None = None, data: Mapping[str, str] | None = None) -> _Response: ...


ClientFactory = Callable[[float], _Client]


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def _default_client_factory(timeout_seconds: float) -> _Client:
    import httpx

    return httpx.Client(timeout=float(timeout_seconds))


def _auth_path(codex_home: Path | None = None) -> Path:
    return Path(codex_home or default_codex_home()).expanduser() / "auth.json"


def _read_auth_payload(codex_home: Path | None = None) -> dict[str, Any]:
    path = _auth_path(codex_home)
    if not path.is_file():
        raise RuntimeError("Codex auth file not found. Run `codex` and sign in first.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("Codex auth file could not be read as JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Codex auth file has invalid shape")
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        raise RuntimeError("Codex auth file is missing tokens. Run `codex` and sign in first.")
    access_token = str(tokens.get("access_token") or "").strip()
    refresh_token = str(tokens.get("refresh_token") or "").strip()
    if not access_token:
        raise RuntimeError("Codex auth file is missing access_token. Run `codex` and sign in first.")
    if not refresh_token:
        raise RuntimeError("Codex auth file is missing refresh_token. Run `codex` and sign in first.")
    return payload


def _write_auth_payload(codex_home: Path | None, payload: dict[str, Any]) -> None:
    path = _auth_path(codex_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _decode_jwt_claims(access_token: Any) -> dict[str, Any]:
    if not isinstance(access_token, str):
        return {}
    parts = access_token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * ((4 - len(payload) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode("utf-8"))
        claims = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    return claims if isinstance(claims, dict) else {}


def _access_token_is_expiring(access_token: Any, skew_seconds: int = CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS) -> bool:
    exp = _decode_jwt_claims(access_token).get("exp")
    if not isinstance(exp, (int, float)):
        return False
    return float(exp) <= (time.time() + max(0, int(skew_seconds)))


def _refresh_tokens_if_needed(
    auth_payload: dict[str, Any],
    *,
    codex_home: Path | None,
    client: _Client,
    force_refresh: bool = False,
) -> dict[str, Any]:
    tokens = dict(auth_payload.get("tokens") or {})
    access_token = str(tokens.get("access_token") or "").strip()
    if not force_refresh and not _access_token_is_expiring(access_token):
        return auth_payload

    refresh_token = str(tokens.get("refresh_token") or "").strip()
    response = client.post(
        CODEX_OAUTH_TOKEN_URL,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CODEX_OAUTH_CLIENT_ID,
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Codex token refresh failed with status {response.status_code}. Run `codex` to sign in again.")
    data = response.json() or {}
    if not isinstance(data, dict):
        raise RuntimeError("Codex token refresh returned invalid JSON")
    new_access = str(data.get("access_token") or "").strip()
    if not new_access:
        raise RuntimeError("Codex token refresh response missing access_token")

    updated_tokens = dict(tokens)
    updated_tokens["access_token"] = new_access
    new_refresh = str(data.get("refresh_token") or "").strip()
    if new_refresh:
        updated_tokens["refresh_token"] = new_refresh
    new_id = str(data.get("id_token") or "").strip()
    if new_id:
        updated_tokens["id_token"] = new_id

    updated_payload = dict(auth_payload)
    updated_payload["tokens"] = updated_tokens
    updated_payload["last_refresh"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_auth_payload(codex_home, updated_payload)
    return updated_payload


def _resolve_codex_usage_url(base_url: str | None = None) -> str:
    normalized = (base_url or os.environ.get("WAYBAR_CODEX_API_BASE_URL") or os.environ.get("CODEX_API_BASE_URL") or DEFAULT_CODEX_BASE_URL).strip().rstrip("/")
    if not normalized:
        normalized = DEFAULT_CODEX_BASE_URL
    if normalized.endswith("/codex"):
        normalized = normalized[: -len("/codex")]
    if "/backend-api" in normalized:
        return normalized + "/wham/usage"
    return normalized + "/api/codex/usage"


def _title_case_slug(value: Any) -> str | None:
    text = str(value or "").replace("_", "-").strip("- ")
    if not text:
        return None
    return " ".join(part.capitalize() for part in text.split("-") if part)


def _main_windows_from_payload(payload: Mapping[str, Any]) -> tuple[Window, ...]:
    rate_limit = payload.get("rate_limit")
    if not isinstance(rate_limit, Mapping):
        rate_limit = payload.get("rate_limits")
    if not isinstance(rate_limit, Mapping):
        return ()

    windows: list[Window] = []
    for keys, label in (
        (("primary_window", "primary"), "Session"),
        (("secondary_window", "secondary"), "Weekly"),
    ):
        raw: Any = None
        for key in keys:
            maybe = rate_limit.get(key)
            if isinstance(maybe, Mapping):
                raw = maybe
                break
        if not isinstance(raw, Mapping):
            continue
        used_raw = raw.get("used_percent")
        if used_raw is None:
            continue
        try:
            used = float(used_raw)
        except (TypeError, ValueError):
            continue
        windows.append(Window(label=label, used_percent=used, reset_at=parse_dt(raw.get("reset_at", raw.get("resets_at")))))
    return tuple(windows)


def _details_from_payload(payload: Mapping[str, Any]) -> tuple[str, ...]:
    details: list[str] = []
    credits = payload.get("credits")
    if isinstance(credits, Mapping) and credits.get("has_credits"):
        balance = credits.get("balance")
        if isinstance(balance, (int, float)):
            details.append(f"Credits balance: ${float(balance):.2f}")
        elif credits.get("unlimited"):
            details.append("Credits balance: unlimited")
    return tuple(details)


def usage_from_codex_api_payload(payload: Mapping[str, Any]) -> Usage:
    windows = _main_windows_from_payload(payload)
    if not windows:
        raise RuntimeError("Codex usage API returned no usable account windows")
    return Usage(
        provider="openai-codex",
        plan=_title_case_slug(payload.get("plan_type")),
        source="Codex usage API",
        fetched_at=utc_now(),
        windows=windows,
        details=_details_from_payload(payload),
        extra_windows=spark_extra_windows_from_payload(payload),
    )


def fetch_via_codex_api(
    codex_home: Path | None = None,
    *,
    base_url: str | None = None,
    client_factory: ClientFactory | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    force_refresh: bool = False,
) -> Usage:
    auth_payload = _read_auth_payload(codex_home)
    factory = client_factory or _default_client_factory
    with factory(float(timeout_seconds)) as client:
        auth_payload = _refresh_tokens_if_needed(
            auth_payload,
            codex_home=codex_home,
            client=client,
            force_refresh=force_refresh,
        )
        tokens = auth_payload.get("tokens") or {}
        access_token = str(tokens.get("access_token") or "").strip()
        account_id = str(tokens.get("account_id") or "").strip()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "codex-cli",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id
        response = client.get(_resolve_codex_usage_url(base_url), headers=headers)
        response.raise_for_status()
        payload = response.json() or {}
    if not isinstance(payload, Mapping):
        raise RuntimeError("Codex usage API returned invalid JSON")
    return usage_from_codex_api_payload(payload)
