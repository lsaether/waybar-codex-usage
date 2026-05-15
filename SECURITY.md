# Security and privacy

`waybar-codex-usage` reads local Codex session logs. Those logs may contain prompts, code, file paths, or project names. Do not upload raw `~/.codex/sessions` files to issues or pull requests.

When reporting parser bugs, create a tiny sanitized fixture that includes only the `token_count.rate_limits` shape needed to reproduce the issue.

The default `logs` backend does not use the network and does not store credentials. The optional Hermes backend delegates account access to an existing Hermes Agent installation and should be treated as best-effort.
