# LLM-Powered AI QA Suite — Claude orientation

> Read first on every session. Scannable. A portfolio suite of AI-powered QA tools built on Claude + the Claude Agent SDK (Python).

## What this repo is

Six independent AI-QA tools, each a small Python package with a `cli.py`, SQLite persistence, and a `tests/` suite:

| Tool | What it does |
| --- | --- |
| `ai-test-generator` | a Jira/GitHub **ticket's acceptance criteria** (`from-jira`) — or a free-text requirement (`generate`) → one traceable Playwright / Cypress / Selenium test per criterion, run + repaired via the closed loop |
| `ai-test-analyzer` | Flaky-test detection + AI root-cause from test logs (batched, structured Pydantic output) |
| `ai-test-healer` | Heals broken selectors against changed DOM |
| `ai-debug-accelerator` | AI-assisted failure debugging |
| `ai-quality-dashboard` | Test-quality metrics + reporting |
| `ai-mock-architect` | GDPR-safe mock/test data generation |

The bar is **production-ready showcase**: it should read as senior work in a 30-second GitHub scan — consistent, typed, tested, honest.

## Stack

Python ≥3.11 · `anthropic` SDK (Claude) · `pydantic` v2 + `pydantic-settings` (structured LLM output + config) · `SQLAlchemy` 2.0 (SQLite) · `tenacity` (retry) · `click` (CLI) · `fastapi`/`uvicorn` (dashboard) · `pytest` + `pytest-cov` · `ruff` (lint+format).

## Commands you'll run most

```bash
.venv/bin/ruff check .                    # lint (must be clean)
.venv/bin/ruff format .                   # format
.venv/bin/pytest -q                       # all tests (must pass, Claude calls mocked)
.venv/bin/pytest ai-test-analyzer -q      # one tool's tests
python3 <tool>/cli.py --help              # a tool's CLI
```

## Project rules (non-negotiable)

- **Type everything.** Public functions carry parameter + return-type hints; `ruff` (+ any type checker) stays clean. No bare `dict`/`Any` where a Pydantic model or `TypedDict` belongs.
- **Structured LLM output via Pydantic**, never fragile hand-parsed JSON. Use the SDK's parse path.
- **Current model IDs** — default `claude-opus-4-8` (or `claude-sonnet-4-6` for cheap/bulk); never hardcode a stale `claude-3-*`. See `.claude/rules/claude-sdk.md`.
- **Tests mock the Claude API** — the suite must test offline + free; a test that hits the real API is wrong.
- **No bare `except:`** — catch specific exceptions; wrap external calls (`anthropic`, DB, network) with `tenacity` retry where transient.
- **One shared pattern, not per-tool sprawl** — the Claude client, DB access, config loading, and CLI scaffolding should be consistent across all six tools (extract a shared core over duplicating).
- **Generated test OUTPUT** (from `ai-test-generator`, Playwright target) follows the `layered-playwright-suite` architecture — see `.claude/rules/generated-output.md`.

## Git / commit rules
- Commit email `juraj.kapusansky@gmail.com`, name `Jurajjjjj1988`; **no `Co-Authored-By: Claude`** / Anthropic attribution (enforced by `.claude/hooks/guard-commit.sh`).
- Branch → PR → merge; never push to `main` without explicit OK.

## Structure
```
<tool>/                cli.py + core modules + tests/ + a per-tool README
  <tool>/db.py         SQLAlchemy models + session (SQLite)
common/                the shared core all tools reuse: claude_client · config · database · models · schemas · sanitizer
pyproject.toml         deps + ruff + pytest config (single source)
.claude/               rules · commands · hooks · agents (this Claude Code setup)
```

## When in doubt
- Conventions: `.claude/rules/{code-style,testing,claude-sdk,generated-output}.md`.
- Each tool's own README for its CLI + scope.
