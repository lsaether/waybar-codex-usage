# waybar-codex-usage

A tiny Codex usage meter for Waybar, built for Hyprland-style Linux desktops.

It emits [Waybar custom module](https://github.com/Alexays/Waybar/wiki/Module:-Custom) JSON like:

```text
CX 21.2% W10.2%
```

- `CX` is the compact Codex label.
- The first percentage is the current/session usage window.
- `W` is the weekly usage window when the selected backend exposes one.
- Spark-specific limits, when exposed by the selected backend, stay out of the compact text and appear only in the tooltip.

The project is intentionally small: no daemon, no telemetry, and Waybar-friendly exit behavior. The default `auto` source is API-first; the explicit `logs` source still works without network access.

> **Backend reality check:** the first-class live backend is the Codex/ChatGPT usage API (`--source codex` / `--source codex-api`). `--source auto` tries Codex directly first, then a stale cached API payload, then local logs.

## Features

- First-class Codex/ChatGPT usage API backend using the installed Codex CLI auth file.
- Keeps an explicit local/offline backend for Codex CLI session JSONL `token_count.rate_limits` snapshots.
- Emits Waybar JSON with `text`, `tooltip`, `class`, `percentage`, and `alt`.
- Caches rendered API payloads, plus explicit `logs` payloads when you select that source.
- Click-refresh friendly with Waybar signals.
- Tooltip-only Spark limit rendering when the backend exposes Spark as a separate additional rate-limit bucket.
- Graceful failure mode: prints `CX --` and exits `0` by default so Waybar does not flap.

## Privacy model

Codex session files can contain prompts, code, paths, and project names. This tool only extracts the `payload.rate_limits` fields from `token_count` events, but you should still treat raw `~/.codex/sessions` files as private.

This tool does **not**:

- send telemetry;
- upload session files;
- print or cache prompts;
- store OAuth tokens in this package;
- require network access for the explicit local-log backend.

When `auto`, `--source codex`, or `--source codex-api` uses the live backend, the tool reads the Codex CLI auth file at `$CODEX_HOME/auth.json` or `~/.codex/auth.json` and calls the Codex/ChatGPT usage endpoint directly. If the access token is expiring, it refreshes it and atomically writes the updated tokens back to the Codex CLI auth file. It does not create a separate credential store.

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

The default Waybar command uses `auto`: native Codex API first, then stale cached API data, then local logs:

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
waybar-codex-usage --source codex
waybar-codex-usage --source auto
waybar-codex-usage --source logs
waybar-codex-usage --sessions-dir ~/.codex/sessions
```

Default source is `auto`. Use `--source logs` or `--offline` when you explicitly want the local Codex CLI session parser. Cache reads are source-aware: API-first runs reuse only cached API payloads, while explicit `logs` runs reuse only local-log payloads. You can also point local mode at a single sanitized JSONL file:

```bash
waybar-codex-usage --source logs --sessions-dir tests/fixtures/codex-session.jsonl
```

### What `logs` / local mode means

Local mode is an offline parser for the Codex CLI JSONL files under `~/.codex/sessions`. It does **not** call OpenAI, and it does not know your account-level subscription state directly. It only reports the newest `payload.rate_limits` snapshot from a local `token_count` event.

That distinction matters because Codex can create recent session files that do not contain `token_count.rate_limits` events, and agent harnesses may use Codex without writing the same local rate-limit snapshots. In those cases, local mode may be missing, old, or marked `stale` even though your real account usage has changed.

Use local mode when you explicitly want a privacy-preserving offline/dev/test backend. For current subscription/account usage, use the native Codex API backend or the default `auto` source:

```bash
waybar-codex-usage --source codex
# or: Codex API first, then stale API cache, then local logs
waybar-codex-usage --source auto
```

## Backend support

`waybar-codex-usage` is API-first by default, with local logs retained as an explicit offline/dev/test backend.

| Source | Status | Network | Auth/token handling | What it reads | Notes |
| --- | --- | --- | --- | --- | --- |
| `codex` / `codex-api` | First-class live backend | Yes | Reads `$CODEX_HOME/auth.json` or `~/.codex/auth.json`; refreshes expiring tokens in that same Codex CLI file | Codex/ChatGPT usage API (`/wham/usage` on the ChatGPT backend) | Best source for current account/subscription usage and Spark additional buckets. Does not create a separate credential store. Requires a prior Codex CLI sign-in. |
| `logs` | Explicit offline/dev/test backend | No | None | Latest `token_count.rate_limits` snapshot from local Codex CLI JSONL sessions | Portable fallback. Only knows what Codex wrote to local logs, so it can be old/stale if recent sessions lack rate-limit snapshots or Codex was run through another harness. If a future/local sanitized snapshot includes Spark under `additional_rate_limits`, Spark is rendered in the tooltip only. |
| `auto` | Default convenience mode | Depends | Same as selected backend | Tries `codex`, then stale cached Codex API output, then `logs` | Not a separate backend; use it when live Codex data is preferred and an older API payload is better than replacing it with local-log estimates. |

Examples:

```bash
waybar-codex-usage --source codex
waybar-codex-usage --source codex-api
waybar-codex-usage --source logs
waybar-codex-usage --source auto
```

Possible future backend work:

- explore a Codex app-server/RPC source if Codex exposes a stable non-interactive route;
- a small backend interface for third-party command/plugin sources;
- parsers for any future official Codex usage export format;
- more sanitized fixtures for new Codex log shapes.

Browser scraping is intentionally not a planned default backend: it is fragile, privacy-sensitive, and a poor fit for a small Waybar module.

### Spark limits

Spark is tracked as a separate additional rate-limit bucket rather than folded into the normal `CX` session/weekly text. Sanitized account-usage payloads currently expose it with fields shaped like:

```json
{
  "additional_rate_limits": [
    {
      "limit_name": "GPT-5.3-Codex-Spark",
      "metered_feature": "codex_bengalfox",
      "rate_limit": {
        "primary_window": {"used_percent": 6, "reset_at": 1778897088, "limit_window_seconds": 18000},
        "secondary_window": {"used_percent": 2, "reset_at": 1779483888, "limit_window_seconds": 604800}
      }
    }
  ]
}
```

When those fields are available, the tooltip adds lines such as `Spark Session: 94% remaining (6% used)` and `Spark Weekly: 98% remaining (2% used)`. The compact text remains backward-compatible by default, e.g. `CX 27% W11%`; Spark does not affect the module `percentage` or warning/critical class.

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `CODEX_HOME` | Codex home directory containing `auth.json` for the live backend | `~/.codex` |
| `CODEX_SESSIONS_DIR` | Codex session log directory | `~/.codex/sessions` |
| `WAYBAR_CODEX_API_BASE_URL` | Advanced override for the Codex/ChatGPT API base URL | `https://chatgpt.com/backend-api/codex` |
| `WAYBAR_CODEX_USAGE_CACHE` | Rendered payload cache path | `$XDG_CACHE_HOME/waybar-codex-usage.json` or `~/.cache/waybar-codex-usage.json` |
| `WAYBAR_CODEX_USAGE_TTL` | Cache TTL seconds | `300` |
| `WAYBAR_CODEX_USAGE_SOURCE` | `codex`, `codex-api`, `logs`, or `auto` | `auto` |

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
uv run waybar-codex-usage --source logs --sessions-dir tests/fixtures/codex-session.jsonl --refresh
```

This package targets Python 3.10+. Runtime dependency: `httpx` for the live Codex API backend.

## Roadmap

- Treat the native Codex API backend as the primary live path.
- Keep the local-log backend stable and boring for explicit offline/dev/test use.
- Add more sanitized fixtures as Codex API/log formats evolve.
- Consider an AUR package only after the CLI shape settles.

## License

MIT. See [`LICENSE`](LICENSE).
