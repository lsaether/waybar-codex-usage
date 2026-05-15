from pathlib import Path

from waybar_codex_usage.codex_logs import latest_local_rate_limit


def test_latest_local_rate_limit_extracts_newest_rate_limit_without_prompt_text():
    usage = latest_local_rate_limit(Path(__file__).parent / "fixtures")

    assert usage.plan == "Pro"
    assert usage.source == "local Codex session log"
    assert usage.stale is True
    assert len(usage.windows) == 2
    assert usage.windows[0].label == "Session"
    assert usage.windows[0].used_percent == 21.2
    assert usage.windows[1].label == "Weekly"
    assert usage.windows[1].used_percent == 10.2
    assert "fake prompt" not in "\n".join(usage.details)


def test_latest_local_rate_limit_fails_cleanly_when_no_events(tmp_path):
    (tmp_path / "empty.jsonl").write_text('{"type":"event_msg","payload":{"type":"token_count"}}\n')

    try:
        latest_local_rate_limit(tmp_path)
    except RuntimeError as exc:
        assert "No local Codex token_count/rate_limits event found" in str(exc) or "no usable windows" in str(exc)
    else:
        raise AssertionError("expected missing rate limits to fail")
