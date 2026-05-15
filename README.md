# waybar-codex-usage

A tiny Codex usage meter for Waybar, built for Hyprland-style Linux desktops.

It emits [Waybar custom module](https://github.com/Alexays/Waybar/wiki/Module:-Custom) JSON like:

```text
CX 21.2% W10.2%
```

- `CX` is the compact Codex label.
- The first percentage is the current/session usage window.
- `W` is the weekly usage window when Codex exposes one in local logs.

The project is intentionally small: Python standard library only at runtime, no daemon, no telemetry, and Waybar-friendly exit behavior.

## Features

- Parses local Codex CLI session JSONL files for `token_count.rate_limits` snapshots.
- Emits Waybar JSON with `text`, `tooltip`, `class`, `percentage`, and `alt`.
- Caches rendered payloads to avoid scanning session logs every poll.
- Click-refresh friendly with Waybar signals.
- Optional Hermes Agent backend for users who already have Hermes configured.
- Graceful failure mode: prints `CX --` and exits `0` by default so Waybar does not flap.

## Privacy model

Codex session files can contain prompts, code, paths, and project names. This tool only extracts the `payload.rate_limits` fields from `token_count` events, but you should still treat raw `~/.codex/sessions` files as private.

This tool does **not**:

- send telemetry;
- upload session files;
- print or cache prompts;
- store OAuth tokens;
- require network access for the default local-log backend.

If you open an issue, please use a sanitized fixture rather than raw Codex session logs.

## Install

From GitHub, once published:

```bash
uv tool install git+https://github.com/lsaether/waybar-codex-usage
```

or:

```bash
pipx install git+https://github.com/lsaether/waybar-codex-usage
```

From a local checkout:

```bash
uv tool install ~/Code/waybar-codex-usage
```

For development:

```bash
git clone https://github.com/lsaether/waybar-codex-usage.git
cd waybar-codex-usage
uv run --with pytest pytest -q
```

## Waybar config

Add a custom module:

```jsonc
"modules-right": ["custom/codex", "pulseaudio", "network", "cpu", "memory", "tray"],

"custom/codex": {
  "exec": "waybar-codex-usage",
  "return-type": "json",
  "interval": 300,
  "signal": 8,
  "tooltip": true,
  "on-click": "waybar-codex-usage --refresh >/dev/null 2>&1; pkill -RTMIN+8 -x waybar"
}
```

If `waybar-codex-usage` is not on Waybar's PATH, use the full path from:

```bash
uv tool dir --bin
```

Example configs live in [`examples/`](examples/).

## CLI usage

```bash
waybar-codex-usage --help
waybar-codex-usage --plain
waybar-codex-usage --refresh
waybar-codex-usage --source logs
waybar-codex-usage --sessions-dir ~/.codex/sessions
```

Default source is `logs`, which parses local Codex CLI session files. You can also point at a single sanitized JSONL file:

```bash
waybar-codex-usage --sessions-dir tests/fixtures/codex-session.jsonl
```

### Optional Hermes backend

If you already run [Hermes Agent](https://hermes-agent.nousresearch.com/docs), you can opt into its OpenAI-Codex usage helper:

```bash
waybar-codex-usage --source hermes
```

or use Hermes first and fall back to local logs:

```bash
waybar-codex-usage --source auto
```

The Hermes backend is optional and best-effort. It imports `agent.account_usage.fetch_account_usage('openai-codex')` from your Hermes checkout. If the upstream account API changes, this backend may break independently of the local-log backend.

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `CODEX_SESSIONS_DIR` | Codex session log directory | `~/.codex/sessions` |
| `WAYBAR_CODEX_USAGE_CACHE` | Rendered payload cache path | `$XDG_CACHE_HOME/waybar-codex-usage.json` or `~/.cache/waybar-codex-usage.json` |
| `WAYBAR_CODEX_USAGE_TTL` | Cache TTL seconds | `300` |
| `WAYBAR_CODEX_USAGE_SOURCE` | `logs`, `hermes`, or `auto` | `logs` |
| `HERMES_AGENT_REPO` | Hermes checkout for optional backend | `~/.hermes/hermes-agent` |

## Waybar classes

The JSON `class` field is one of:

- `ok`
- `warning` — highest known usage >= 80%
- `critical` — highest known usage >= 95%
- `stale` — local/cached fallback data
- `error` — no usable data

CSS example:

```css
#custom-codex {
  padding: 0 10px;
  color: #9ad7a6;
  border-left: 1px solid rgba(120, 170, 130, 0.35);
}

#custom-codex.warning { color: #d8c56d; }
#custom-codex.critical,
#custom-codex.error { color: #e06c75; }
#custom-codex.stale { color: #7f9f86; }
```

## Development

```bash
uv run --with pytest pytest -q
uv build
uv run waybar-codex-usage --sessions-dir tests/fixtures/codex-session.jsonl --refresh
```

This package targets Python 3.10+ and has no runtime dependencies.

## Roadmap

- Keep the local-log backend stable and boring.
- Add more sanitized fixtures as Codex log formats evolve.
- Keep the Hermes/direct-account backend optional and clearly experimental.
- Consider an AUR package only after the CLI shape settles.

## License

MIT. See [`LICENSE`](LICENSE).
