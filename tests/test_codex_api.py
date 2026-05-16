import base64
import json
from datetime import datetime, timezone

from waybar_codex_usage.codex_api import fetch_via_codex_api


def _jwt_with_exp(exp: int) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.sig"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, *, headers):
        self.calls.append(("GET", url, headers, None))
        return self.responses.pop(0)

    def post(self, url, *, headers=None, data=None):
        self.calls.append(("POST", url, headers or {}, data or {}))
        return self.responses.pop(0)


def _api_payload():
    return {
        "plan_type": "pro",
        "rate_limit": {
            "primary_window": {"used_percent": 31.5, "reset_at": "2026-05-15T16:00:00Z"},
            "secondary_window": {"used_percent": 14, "reset_at": "2026-05-22T16:00:00Z"},
        },
        "additional_rate_limits": [
            {
                "limit_name": "GPT-5.3-Codex-Spark",
                "metered_feature": "codex_bengalfox",
                "rate_limit": {
                    "primary_window": {"used_percent": 6, "reset_at": "2026-05-15T13:00:00Z"},
                    "secondary_window": {"used_percent": 2, "reset_at": "2026-05-22T13:00:00Z"},
                },
            }
        ],
        "credits": {"has_credits": True, "balance": 12.34},
    }


def test_codex_api_reads_codex_cli_auth_and_normalizes_usage(tmp_path):
    (tmp_path / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "account_id": "acct-test",
                }
            }
        )
    )
    client = FakeClient([FakeResponse(_api_payload())])

    usage = fetch_via_codex_api(codex_home=tmp_path, client_factory=lambda timeout: client)

    assert usage.source == "Codex usage API"
    assert usage.provider == "openai-codex"
    assert usage.plan == "Pro"
    assert [(w.label, w.used_percent) for w in usage.windows] == [("Session", 31.5), ("Weekly", 14.0)]
    assert [(w.label, w.used_percent) for w in usage.extra_windows] == [("Spark Session", 6.0), ("Spark Weekly", 2.0)]
    assert usage.details == ("Credits balance: $12.34",)
    assert client.calls[0][0] == "GET"
    assert client.calls[0][1] == "https://chatgpt.com/backend-api/wham/usage"
    assert client.calls[0][2]["Authorization"] == "Bearer access-token"
    assert client.calls[0][2]["ChatGPT-Account-Id"] == "acct-test"


def test_codex_api_refreshes_expiring_codex_cli_token_and_preserves_auth_file(tmp_path):
    (tmp_path / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _jwt_with_exp(1),
                    "refresh_token": "old-refresh-token",
                    "account_id": "acct-test",
                },
            }
        )
    )
    client = FakeClient(
        [
            FakeResponse({"access_token": "new-access-token", "refresh_token": "new-refresh-token"}),
            FakeResponse(_api_payload()),
        ]
    )

    usage = fetch_via_codex_api(codex_home=tmp_path, client_factory=lambda timeout: client)

    assert usage.windows[0].used_percent == 31.5
    assert client.calls[0][0] == "POST"
    assert client.calls[0][1] == "https://auth.openai.com/oauth/token"
    assert client.calls[0][3]["grant_type"] == "refresh_token"
    assert client.calls[0][3]["refresh_token"] == "old-refresh-token"
    assert client.calls[1][2]["Authorization"] == "Bearer new-access-token"
    saved = json.loads((tmp_path / "auth.json").read_text())
    assert saved["auth_mode"] == "chatgpt"
    assert saved["tokens"]["access_token"] == "new-access-token"
    assert saved["tokens"]["refresh_token"] == "new-refresh-token"
    assert saved["tokens"]["account_id"] == "acct-test"
