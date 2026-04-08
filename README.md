# LLM-Powered AI QA Suite

Six AI-powered QA tools built on **Claude** and the **Claude Agent SDK** — from generating tests and healing broken selectors to root-causing flaky failures and producing GDPR-safe mock data. A portfolio of AI-native quality engineering: each tool a small, typed, tested Python package on a shared core.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Claude Agent SDK](https://img.shields.io/badge/Claude%20Agent%20SDK-D97757)](https://docs.anthropic.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-structured%20outputs-E92063)](https://docs.pydantic.dev/)
[![ruff](https://img.shields.io/badge/ruff-clean-261230?logo=ruff)](https://docs.astral.sh/ruff/)
[![tests](https://img.shields.io/badge/pytest-128%20passing-0A9EDC?logo=pytest&logoColor=white)](#quality)

**Demonstrates:** structured LLM outputs (Pydantic) · a shared Claude client with retry + caching · packaged multi-tool Python · a full Claude Code project setup — not throwaway scripts.

---

## Tools

| Tool | What it does | CLI |
| --- | --- | --- |
| **ai-test-generator** | Plain-English requirement → Playwright / Cypress / Selenium test code (cached by requirement hash, structurally validated before persisting) | `ai-test-generator generate "user can log in" --framework playwright` |
| **ai-test-analyzer** | Detects flaky tests from run logs + AI root-cause with fix suggestions (batched, structured output) | `cat runs.json \| ai-test-analyzer analyze -` |
| **ai-test-healer** | Heals a broken selector against the changed DOM, validating the CSS before recording it | `ai-test-healer heal "login button" ".old" "<html>…"` |
| **ai-debug-accelerator** | AI-assisted triage of a failing test — likely cause + next step | `ai-debug-accelerator analyze failure.log` |
| **ai-mock-architect** | GDPR-safe synthetic/mock test data from a schema | `ai-mock-architect generate schema.json` |
| **ai-quality-dashboard** | Read-only FastAPI dashboard over the tools' metrics | `ai-quality-dashboard serve` |

Every tool persists to a shared SQLite DB and talks to Claude only through `common/claude_client.py`.

## Quickstart

```bash
git clone https://github.com/Jurajjjjj1988/LLM-Powered-AI-QA-Suite.git
cd LLM-Powered-AI-QA-Suite
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # installs the tools + their CLIs
export ANTHROPIC_API_KEY=sk-ant-...                          # or a .env file
ai-test-generator generate "User can reset their password" --framework playwright
```

Each tool becomes a console entry point after install (`ai-test-generator`, `ai-test-analyzer`, …). Run any with `--help`.

## Architecture

```
common/                shared core — every tool reuses it (never re-implemented)
  claude_client.py       the ONE Claude wrapper (retry, caching, structured output)
  config.py              pydantic-settings config (env / .env)
  database.py            SQLAlchemy 2.0 sessions (SQLite)
  models.py schemas.py   ORM models + pydantic request/response DTOs
  sanitizer.py           input sanitisation (prompt-injection separation)
ai_test_generator/     one package per tool: cli.py · core · prompts · repository · tests/
ai_test_analyzer/      …  imports are namespaced (ai_test_analyzer.prompts) — no cross-tool collisions
…
.claude/               Claude Code project setup — rules · commands · hooks · agents
```

- **Structured, not string-parsed.** LLM responses come back as validated Pydantic models via the SDK's parse path, never hand-parsed JSON.
- **One shared pattern.** The Claude client, DB, config, and CLI scaffolding live in `common/`; a tool never imports `anthropic` or touches SQLite directly.
- **Packaged.** Each tool is a real Python package with a console entry point — installable, importable, and free of the flat-module collisions a multi-tool repo invites.

## Quality

| Gate | State |
| --- | --- |
| `ruff check .` | **clean** (lint + format) |
| `pytest` | **128 passing** · 13 skipped (the dashboard API harness is mid-refactor — see Roadmap) |
| Types | typed public surface (return + parameter hints); `common/` fully typed |
| Claude API in tests | fully **mocked** — the suite runs offline + free |

```bash
.venv/bin/ruff check . && .venv/bin/pytest -q
```

## Roadmap

The current tools are open-loop analysers. The strongest next step is a **closed loop** — the pattern from the sibling [PWmodernizer](https://github.com/Jurajjjjj1988/PWmodernizer): generate → **run** the test → **repair** on failure until it actually passes. Building a shared execution runner in `common/` once unlocks it across the generator, healer, and a planned mutation-testing tool. Also queued: a requirements→test coverage cartographer, an LLM-app / prompt-evaluation tool, and the FastAPI dashboard's dependency-injection refactor (the skipped tests).

## Limitations (honest)

- **Assistive, human-reviewed** — the tools produce a strong first pass, not merge-ready output unattended. LLM test-generation accuracy tops out around ~85%.
- No execution/verification loop yet (see Roadmap) — generated tests are structurally validated, not run.
- The dashboard's API tests are skipped pending a lifespan + dependency-override refactor.

## License

MIT. See [`LICENSE`](LICENSE).
