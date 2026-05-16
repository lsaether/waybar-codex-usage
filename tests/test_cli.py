import json
from pathlib import Path

from waybar_codex_usage.cli import main


def test_cli_outputs_waybar_json_from_local_logs(capsys, tmp_path):
    fixture_dir = Path(__file__).parent / "fixtures"

    rc = main(["--source", "logs", "--sessions-dir", str(fixture_dir), "--cache", str(tmp_path / "cache.json"), "--refresh"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "CX 21.2% W10.2%"
    assert payload["class"] == "stale"


def test_cli_outputs_spark_only_in_tooltip_from_sanitized_fixture(capsys, tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "codex-session-with-spark.jsonl"

    rc = main(["--source", "logs", "--sessions-dir", str(fixture), "--cache", str(tmp_path / "cache.json"), "--refresh"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "CX 27% W11%"
    assert "Spark Session: 94% remaining (6% used)" in payload["tooltip"]
    assert "Spark Weekly: 98% remaining (2% used)" in payload["tooltip"]


def test_cli_source_codex_uses_first_class_codex_api(monkeypatch, capsys, tmp_path):
    from datetime import datetime, timezone

    from waybar_codex_usage.models import Usage, Window

    def fake_codex_api(codex_home=None):
        assert codex_home == tmp_path / "codex-home"
        return Usage(
            provider="openai-codex",
            plan="Pro",
            source="Codex usage API",
            fetched_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
            windows=(Window("Session", 33), Window("Weekly", 12)),
        )

    monkeypatch.setattr("waybar_codex_usage.cli.fetch_via_codex_api", fake_codex_api)

    rc = main([
        "--source",
        "codex",
        "--codex-home",
        str(tmp_path / "codex-home"),
        "--cache",
        str(tmp_path / "cache.json"),
        "--refresh",
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "CX 33% W12%"
    assert "Source: Codex usage API" in payload["tooltip"]


def test_cli_auto_prefers_codex_api_before_hermes_and_logs(monkeypatch, capsys, tmp_path):
    from datetime import datetime, timezone

    from waybar_codex_usage.models import Usage, Window

    calls = []

    def fake_codex_api(codex_home=None):
        calls.append("codex")
        return Usage(
            provider="openai-codex",
            plan="Pro",
            source="Codex usage API",
            fetched_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
            windows=(Window("Session", 44),),
        )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("fallback source should not be called")

    monkeypatch.setattr("waybar_codex_usage.cli.fetch_via_codex_api", fake_codex_api)
    monkeypatch.setattr("waybar_codex_usage.cli.fetch_via_hermes", fail_if_called)
    monkeypatch.setattr("waybar_codex_usage.cli.latest_local_rate_limit", fail_if_called)

    rc = main(["--source", "auto", "--cache", str(tmp_path / "cache.json"), "--refresh"])

    assert rc == 0
    assert calls == ["codex"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "CX 44%"
    assert "Source: Codex usage API" in payload["tooltip"]


def test_cli_auto_falls_back_from_codex_to_hermes(monkeypatch, capsys, tmp_path):
    from datetime import datetime, timezone

    from waybar_codex_usage.models import Usage, Window

    calls = []

    def fake_codex_api(codex_home=None):
        calls.append("codex")
        raise RuntimeError("codex unavailable")

    def fake_hermes(hermes_repo=None):
        calls.append("hermes")
        return Usage(
            provider="openai-codex",
            plan="Pro",
            source="Hermes OpenAI-Codex usage helper",
            fetched_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
            windows=(Window("Session", 55),),
        )

    monkeypatch.setattr("waybar_codex_usage.cli.fetch_via_codex_api", fake_codex_api)
    monkeypatch.setattr("waybar_codex_usage.cli.fetch_via_hermes", fake_hermes)

    rc = main(["--source", "auto", "--cache", str(tmp_path / "cache.json"), "--refresh"])

    assert rc == 0
    assert calls == ["codex", "hermes"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "CX 55%"
    assert "Source: Hermes OpenAI-Codex usage helper" in payload["tooltip"]


def test_cli_auto_falls_back_from_codex_and_hermes_to_logs(monkeypatch, capsys, tmp_path):
    fixture_dir = Path(__file__).parent / "fixtures"
    calls = []

    def fake_codex_api(codex_home=None):
        calls.append("codex")
        raise RuntimeError("codex unavailable")

    def fake_hermes(hermes_repo=None):
        calls.append("hermes")
        raise RuntimeError("hermes unavailable")

    monkeypatch.setattr("waybar_codex_usage.cli.fetch_via_codex_api", fake_codex_api)
    monkeypatch.setattr("waybar_codex_usage.cli.fetch_via_hermes", fake_hermes)

    rc = main([
        "--source",
        "auto",
        "--sessions-dir",
        str(fixture_dir),
        "--cache",
        str(tmp_path / "cache.json"),
        "--refresh",
    ])

    assert rc == 0
    assert calls == ["codex", "hermes"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "CX 21.2% W10.2%"
    assert "Source: local Codex session log" in payload["tooltip"]


def test_cli_waybar_friendly_errors_exit_zero(capsys, tmp_path):
    rc = main(["--source", "logs", "--sessions-dir", str(tmp_path / "missing"), "--cache", str(tmp_path / "cache.json"), "--refresh"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "CX --"
    assert payload["class"] == "error"


def test_offline_bypasses_cached_online_payload(capsys, tmp_path):
    fixture_dir = Path(__file__).parent / "fixtures"
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"text": "CX CACHED", "tooltip": "Source: cached API", "class": "ok"}))

    rc = main(["--offline", "--sessions-dir", str(fixture_dir), "--cache", str(cache)])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "CX 21.2% W10.2%"
    assert "Source: local Codex session log" in payload["tooltip"]
