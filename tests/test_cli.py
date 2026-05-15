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
