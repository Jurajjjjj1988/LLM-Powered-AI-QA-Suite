# LLM-Powered AI QA Suite

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Claude Agent SDK](https://img.shields.io/badge/Claude%20Agent%20SDK-D97757)](https://docs.anthropic.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-structured%20outputs-E92063)](https://docs.pydantic.dev/)
[![ruff](https://img.shields.io/badge/ruff-clean-261230?logo=ruff)](https://docs.astral.sh/ruff/)
[![tests](https://img.shields.io/badge/pytest-155%20passing%20%C2%B7%200%20skipped-0A9EDC?logo=pytest&logoColor=white)](#quality)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Six AI-powered QA tools on **Claude** + the **Claude Agent SDK** — generate, heal, analyse, debug, mock. **Catches the failure open-loop AI tools miss: a generated test that compiles but never runs.** The flagship generator closes the loop — *generate → run → repair until it actually passes*.

> [!TIP]
> Jump to [What each tool catches](#what-each-tool-catches) — every row answers *"what QA problem slips into production if this tool didn't exist?"*, not "what does it do".

## Quick start

```bash
git clone https://github.com/Jurajjjjj1988/LLM-Powered-AI-QA-Suite.git
cd LLM-Powered-AI-QA-Suite
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # installs the tools + their CLIs
export ANTHROPIC_API_KEY=sk-ant-...                          # or a .env file

ai-test-generator generate "User can reset their password" --framework playwright
# closed loop — run the generated test against a live app + repair until green:
ai-test-generator generate "add item to cart" --output-file cart.spec.ts --url https://shop.example
```

## What each tool catches

| Tool | Bug-class it attacks (what slips if absent) | How | Loop |
| --- | --- | --- | :--: |
| **ai-test-generator** | AI writes a test that *compiles but never runs* — the classic open-loop tell | English → layered page-object Playwright/Cypress/Selenium, then **runs + repairs** it against a live app | 🔁 **closed** |
| **ai-test-healer** | a UI change silently breaks a selector, tests go red for the wrong reason | proposes a working selector against the new DOM, CSS-validated | open |
| **ai-test-analyzer** | flaky tests erode trust in CI | flaky detection + AI root-cause from run logs (structured, batched) | open |
| **ai-debug-accelerator** | failure triage is manual + slow | likely cause + next step from a failure log | open |
| **ai-mock-architect** | test data is unsafe (PII) or tedious | GDPR-safe synthetic data from a schema | open |
| **ai-quality-dashboard** | the suite's metrics are scattered | read-only FastAPI view over all tools' data | — |

## Techniques (how it's built)

| Code | Technique | Where |
| --- | --- | --- |
| `[LOOP]` | closed loop `generate → run → repair`, trustworthy verdict | `common/test_runner.py` + `TestGenerator.generate_and_verify` |
| `[STRUCT]` | Pydantic structured LLM output — validated model, never hand-parsed JSON | `common/claude_client.py`, `common/schemas.py` |
| `[CORE]` | one shared Claude client / DB / config for all six tools | `common/` |
| `[GATE]` | validator (stable selectors, no `.nth()` / hard waits) + `ruff` + `pytest` | `ai_test_generator/validator.py` |
| `[DI]` | FastAPI dependency injection, overridden in tests (no reload hacks) | `ai_quality_dashboard/` |
| `[SAFE]` | `tenacity` retry on transient errors + prompt-injection sanitisation | `common/` |

## What a closed-loop run looks like

```
$ ai-test-generator generate "add item to cart" --output-file cart.spec.ts --url https://shop.example
Generation complete  [source=Claude API  validation=PASSED  tokens=…]
Written to: cart.spec.ts
Closed loop: execution=GREEN  repairs=1
```

A **red** run feeds the real failure output back to the model, re-writes the spec, and re-runs — accepting only a *genuine* pass (`exit 0` AND `≥1 passed` AND `0 failed/flaky/timed-out`). A bare `"passed"` in a title, or an all-skipped run, never counts as green — the same false-green defence proven in the sibling [PWmodernizer](https://github.com/Jurajjjjj1988/PWmodernizer).

## Quality

| Gate | State |
| --- | --- |
| `ruff check .` | **clean** (lint + format) |
| `pytest` | **155 passing · 0 skipped** — the Claude API is fully mocked, so tests run offline + free |
| Types | **100%** of public functions carry a return-type annotation (AST-verified) |

```bash
.venv/bin/ruff check . && .venv/bin/pytest -q
```

## Architecture

```
common/                shared core — every tool reuses it, never re-implements it
  claude_client.py       the ONE Claude wrapper (retry · caching · structured output)
  test_runner.py         the closed-loop primitive (run a spec → trustworthy verdict)
  config · database · models · schemas · sanitizer
ai_test_generator/     one PACKAGE per tool: cli.py · core · prompts · repository · tests/
…                      each tool = a console entry point (ai-test-generator, …)
.claude/               Claude Code project setup — rules · commands · hooks · agents
```

Full design + the theory behind it (open-loop vs closed-loop, structured outputs, mutation testing, gates-as-trust): **[`AI-QA-SUITE/DESIGN-PROCESS-AND-THEORY.md`](AI-QA-SUITE/DESIGN-PROCESS-AND-THEORY.md)**.

## What it does NOT catch (honest)

The seniority signal is naming the blind spots, not overclaiming coverage:

- **A generated test only truly closes the loop with a target app.** Pass `--url` + have Node/Playwright installed; without one, output is structurally validated, not executed.
- **~85% LLM-accuracy ceiling** — the tools produce a strong first pass under **human review**, not merge-ready output unattended.
- **No visual / performance / accessibility / mutation coverage yet** — those are the queued tools (Roadmap), not silently implied.
- **Non-deterministic backends** make any single run's pass/fail unreliable — baseline the app first.

## Roadmap

The shared execution runner (`common/test_runner.py`) is the lever: build it once, and each queued tool reuses it — **mutation-sentinel** (test *effectiveness*, not just pass/fail), **coverage-cartographer** (requirements → test traceability), **healer verify-loop**, **triage-bot** (auto-quarantine), **prompt-guardian** (test LLM-powered *apps*).

## License

MIT. See [`LICENSE`](LICENSE).
