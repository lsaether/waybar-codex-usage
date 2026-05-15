# Contributing

Keep the tool small, boring, and privacy-preserving.

## Local checks

```bash
uv run --with pytest pytest -q
uv build
```

## Fixtures

Do not commit raw Codex session logs. Tests should use hand-written, sanitized JSONL fixtures that include only the fields required by the parser.

## Runtime dependencies

The package should remain Python-standard-library only at runtime unless there is a strong reason to change that.
