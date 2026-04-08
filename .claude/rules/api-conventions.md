# API & CLI conventions

**CLIs (Click):** every tool exposes `cli.py` with a `click.group()` and verb subcommands (`generate`, `analyze`, `heal`). Read `-` from stdin where a file is expected. Exit non-zero on failure. `--help` is complete. No `print()` for machine output — use the shared logger or JSON to stdout.

**FastAPI (ai-quality-dashboard):** request/response bodies are Pydantic models (never bare dict). Errors return a typed problem shape with an HTTP status, never a 200 with an error string. Version routes under `/api/v1`. No blocking calls in async handlers — offload Claude calls to a thread/executor.

**Shared:** all Claude access goes through `common/claude_client.py`; all persistence through `common/database.py` — a tool never talks to `anthropic` or SQLite directly.
