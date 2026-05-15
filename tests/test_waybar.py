from datetime import datetime, timezone

from waybar_codex_usage.models import Usage, Window
from waybar_codex_usage.waybar import usage_to_waybar, waybar_class


def test_waybar_payload_is_compact_and_includes_tooltip_details():
    usage = Usage(
        provider="openai-codex",
        plan="Pro",
        source="local Codex session log",
        fetched_at=datetime(2026, 5, 15, 10, 2, tzinfo=timezone.utc),
        windows=(
            Window("Session", used_percent=21.2),
            Window("Weekly", used_percent=10.2),
        ),
        stale=True,
    )

    payload = usage_to_waybar(usage)

    assert payload["text"] == "CX 21.2% W10.2%"
    assert payload["class"] == "stale"
    assert payload["percentage"] == 21
    assert payload["alt"] == "codex"
    assert "Codex usage · Pro" in payload["tooltip"]
    assert "Session: 79% remaining (21.2% used)" in payload["tooltip"]
    assert "Source: local Codex session log" in payload["tooltip"]


def test_waybar_class_warns_and_criticals_on_high_usage():
    assert waybar_class(Usage("openai-codex", None, "test", datetime.now(timezone.utc), (Window("Session", 80),))) == "warning"
    assert waybar_class(Usage("openai-codex", None, "test", datetime.now(timezone.utc), (Window("Session", 95),))) == "critical"
    assert waybar_class(Usage("openai-codex", None, "test", datetime.now(timezone.utc), (), error="boom")) == "error"
