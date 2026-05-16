# Changelog

## 0.1.0

- Initial package scaffold.
- Local Codex JSONL `token_count.rate_limits` parser.
- Waybar JSON renderer.
- Cache, click-refresh, plain-text, and Waybar-friendly error output.
- First-class native Codex API backend (`--source codex` / `--source codex-api`) using Codex CLI auth.
- Removed the deprecated Hermes Agent compatibility backend.
- `--source auto` now tries Codex API, then local logs.
- Tooltip-only Spark limit rendering from separate `additional_rate_limits` buckets.
