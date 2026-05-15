import shlex
import stat
import sys

from waybar_codex_usage.hermes_backend import fetch_via_hermes


def test_hermes_backend_uses_hermes_python_when_current_env_lacks_deps(monkeypatch, tmp_path):
    repo = tmp_path / "hermes-agent"
    agent_dir = repo / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "__init__.py").write_text("")
    (agent_dir / "account_usage.py").write_text(
        '''
import os
from datetime import datetime, timezone

if os.environ.get("FAKE_HERMES_SUBPROCESS") != "1":
    import missing_httpx_like_dependency

class RawWindow:
    label = "Session"
    used_percent = 12.5
    reset_at = datetime(2026, 5, 15, 12, 30, tzinfo=timezone.utc)
    detail = "test detail"

class Snapshot:
    available = True
    provider = "openai-codex"
    plan = "Pro"
    windows = (RawWindow(),)
    details = ("from fake Hermes",)

def fetch_account_usage(provider):
    assert provider == "openai-codex"
    return Snapshot()
'''
    )

    wrapper = tmp_path / "hermes-python"
    wrapper.write_text(
        "#!/bin/sh\n"
        "export FAKE_HERMES_SUBPROCESS=1\n"
        f"exec {shlex.quote(sys.executable)} \"$@\"\n"
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)

    monkeypatch.setenv("HERMES_AGENT_PYTHON", str(wrapper))
    try:
        usage = fetch_via_hermes(repo)
    finally:
        sys.modules.pop("agent.account_usage", None)
        sys.modules.pop("agent", None)

    assert usage.source == "Hermes OpenAI-Codex usage helper"
    assert usage.plan == "Pro"
    assert usage.windows[0].label == "Session"
    assert usage.windows[0].used_percent == 12.5
    assert usage.details == ("from fake Hermes",)
