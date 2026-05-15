# waybar-codex-usage

A tiny Codex usage meter for Waybar, built for Hyprland-style Linux desktops.

It emits [Waybar custom module](https://github.com/Alexays/Waybar/wiki/Module:-Custom) JSON like:

```text
CX 21.2% W10.2%
```

- `CX` is the compact Codex label.
- The first percentage is the current/session usage window.
- `W` is the weekly usage window when the selected backend exposes one.

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

If you already have Hermes Agent installed/configured and want account-level/live subscription usage, prefer the Hermes helper or `auto` mode in Waybar:

```jsonc
"custom/codex": {
  "exec": "waybar-codex-usage --source auto",
  "return-type": "json",
  "interval": 300,
  "signal": 8,
  "tooltip": true,
  "on-click": "waybar-codex-usage --source auto --refresh >/dev/null 2>&1; pkill -RTMIN+8 -x waybar"
}
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

### What `logs` / local mode means

Local mode is an offline parser for the Codex CLI JSONL files under `~/.codex/sessions`. It does **not** call OpenAI or Hermes, and it does not know your account-level subscription state directly. It only reports the newest `payload.rate_limits` snapshot from a local `token_count` event.

That distinction matters because Codex can create recent session files that do not contain `token_count.rate_limits` events, and agent harnesses may use Codex without writing the same local rate-limit snapshots. In those cases, local mode may be missing, old, or marked `stale` even though your real account usage has changed.

Use local mode when you want a dependency-free, privacy-preserving offline fallback. If you already have Hermes Agent installed/configured and want current subscription/account usage, enable the Hermes helper instead:

```bash
waybar-codex-usage --source hermes
# or: Hermes first, local logs as fallback
waybar-codex-usage --source auto
```

## Backend support

`waybar-codex-usage` is local-first. Version `0.1` is feature-complete for the local log parser; account-level backends are optional and intentionally conservative.

| Source | Status | Network | Auth/token handling | What it reads | Notes |
| --- | --- | --- | --- | --- | --- |
| `logs` | Stable default | No | None | Latest `token_count.rate_limits` snapshot from local Codex CLI JSONL sessions | Portable offline fallback. Only knows what Codex wrote to local logs, so it can be old/stale if recent sessions lack rate-limit snapshots or Codex was run through another harness. |
| `hermes` | Optional / experimental | Usually | Delegated to an existing Hermes Agent checkout | `agent.account_usage.fetch_account_usage("openai-codex")` | Requires Hermes Agent installed/configured locally with OpenAI-Codex auth. Does not require a Hermes TUI/gateway/daemon to be running. This package does not store OAuth tokens. It imports Hermes directly when dependencies are available, otherwise it tries the Hermes venv Python. Can break if Hermes or the upstream account API changes. |
| `auto` | Convenience mode | Depends | Same as selected backend | Tries `hermes`, then falls back to `logs` | Not a separate backend; good for personal machines where live Hermes usage is preferred when Hermes is available, but stale local data is better than a hard error. On machines without Hermes, it behaves as local-log fallback. |

Examples:

```bash
waybar-codex-usage --source logs
waybar-codex-usage --source hermes
waybar-codex-usage --source auto
```

Possible future backend work:

- first-class direct Codex/OpenAI account API backend, if the auth and endpoint contract becomes stable enough to document safely; this would be the path for live account usage without requiring Hermes Agent;
- a small backend interface for third-party command/plugin sources;
- parsers for any future official Codex usage export format;
- more sanitized fixtures for new Codex log shapes.

Browser scraping is intentionally not a planned default backend: it is fragile, privacy-sensitive, and a poor fit for a small Waybar module.

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `CODEX_SESSIONS_DIR` | Codex session log directory | `~/.codex/sessions` |
| `WAYBAR_CODEX_USAGE_CACHE` | Rendered payload cache path | `$XDG_CACHE_HOME/waybar-codex-usage.json` or `~/.cache/waybar-codex-usage.json` |
| `WAYBAR_CODEX_USAGE_TTL` | Cache TTL seconds | `300` |
| `WAYBAR_CODEX_USAGE_SOURCE` | `logs`, `hermes`, or `auto` | `logs` |
| `HERMES_AGENT_REPO` | Hermes checkout for optional backend | `~/.hermes/hermes-agent` |
| `HERMES_AGENT_PYTHON` | Python executable to run the Hermes backend with, useful when Hermes dependencies live in its venv | first existing of `<repo>/venv/bin/python3`, `<repo>/venv/bin/python`, `<repo>/.venv/bin/python3`, `<repo>/.venv/bin/python` |
| `WAYBAR_CODEX_HERMES_TIMEOUT` | Hermes backend subprocess timeout seconds | `25` |

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
