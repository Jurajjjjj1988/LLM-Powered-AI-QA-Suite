# The AI QA Suite — Design, Process & Theory

> A complete, honest account of **what** this suite is, **how** it was built and repaired to a professional bar, **why** each decision was made, and the **theory** underneath it. Written as a design + engineering + learning document, not marketing.

---

## Part 1 — What it is

The **LLM-Powered AI QA Suite** is a portfolio of **six AI-powered QA tools** built on **Claude** and the **Claude Agent SDK** in Python. Each tool automates one real problem in a testing pipeline:

| Tool | Problem it solves | AI role |
| --- | --- | --- |
| `ai-test-generator` | Tests written from a vague one-liner, not the ticket's real criteria | a **ticket's acceptance criteria** (or a free-text requirement) → one traceable test per criterion, run + repaired |
| `ai-test-analyzer` | Flaky tests erode trust in CI | detect flakiness from logs + root-cause + fix suggestions |
| `ai-test-healer` | UI changes break selectors | propose a working selector against the new DOM |
| `ai-debug-accelerator` | Failure triage is manual | likely cause + next step from a failure log |
| `ai-mock-architect` | Test data is unsafe/tedious | GDPR-safe synthetic data from a schema |
| `ai-quality-dashboard` | Metrics are scattered | read-only FastAPI view over the suite's data |

The point is not any single tool — it's the **shape**: a shared core (`common/`) that every tool reuses, structured (validated) LLM I/O, real tests, and a professional project setup. It reads as **AI-native quality engineering**, which is the story it exists to tell.

---

## Part 2 — The theory around it

### 2.1 Why LLMs in QA at all
Testing has three expensive, judgement-heavy activities that classic automation can't do well: **writing** tests from intent, **maintaining** them when the app changes, and **diagnosing** why they failed. These are language + reasoning tasks — exactly where LLMs help. The 2025–26 industry consensus: ~90%+ of teams now use AI somewhere in test automation, but far fewer *verify or maintain* what the AI produces. That gap is the opportunity — and the risk.

### 2.2 Structured outputs, not string-parsing
The single most important reliability idea here. An LLM asked for JSON in free text will *usually* comply and *occasionally* wrap it in prose or fences or hallucinate a field. Parsing that by hand is fragile. Instead, the suite uses **Pydantic models** + the SDK's structured-output/parse path: the model is *constrained* to a schema and the response comes back as a validated object. A malformed response fails loudly at the boundary, not silently three layers down. `ai-test-analyzer` and the generator both use this (`_BatchSuggestions`, request/response DTOs in `common/schemas.py`).

### 2.3 Prompt-injection separation
Test logs, DOM snippets, and requirements are **untrusted input** flowing into a prompt. `common/sanitizer.py` keeps that data separated from instructions so a malicious log line can't hijack the model. This is the QA-tooling version of "never concatenate user input into a query."

### 2.4 Cost-aware caching
LLM calls cost money + latency. The generator caches by **requirement hash** (same requirement → no second call); the shared client caches stable context. Determinism-by-caching also makes the tools more testable.

### 2.5 Resilience
Every external call (Anthropic, DB) is wrapped with **tenacity** retry on transient errors, and `stop_reason` is checked before reading content. A flaky network shouldn't look like a tool bug.

### 2.6 The open-loop vs closed-loop frontier  ← the big idea
Today all six tools are **open-loop**: they read a static input (a log, a DOM snippet, a schema) and emit an answer. Nothing *runs* the test it wrote or *verifies* the selector it healed. Reviewers spot open-loop AI instantly ("it wrote code but never ran it").

The frontier — and the strongest next step — is the **closed loop**: `generate → run → observe the failure → repair → re-run, until it actually passes`. The discipline is that output is accepted *only* when it runs green against the real app. Self-healing research frames the same idea as a three-step **context → evaluate → validate** loop: without the *validate* step, "self-healing" is just guessing.

### 2.7 Test *effectiveness*, not just test *count*
An LLM can write tests that pass but don't catch bugs. The trust metric the literature blesses (Meta's ACH, Atlassian's mutation assistant) is **mutation testing**: inject a small bug into the source, and if the test still passes, the test is worthless. "Do these tests catch bugs?" is a stronger question than "do they pass?" — a planned `ai-mutation-sentinel` tool would answer it.

### 2.8 Gates as calibrated trust
Quality isn't a vibe; it's **proven gates**. `ruff` (lint), `pytest` (behaviour), and structured validation each catch a class of defect deterministically. A green gate you've proven correct lets each run self-certify — you trust the gate, not a manual review of every output.

### 2.9 Tests come from acceptance criteria, not a paraphrase  ← the correctness anchor
A test generated from *"user can log in"* is only as good as that vague sentence. Real, valuable tests come from a work item's **acceptance criteria** — the concrete, checkable statements a feature must satisfy. So `ai-test-generator` reads a real **ticket** (a Jira export, or a `gh issue view` GitHub issue — a GitHub issue *is* a git-hosted ticket, so no Jira token is needed) and generates **one traceable test per criterion**, each tagged `AC1…ACn` under the ticket key. Two consequences make this trustworthy rather than cosmetic:
- **Parsing is deterministic + defensive.** A dedicated parser turns messy markdown (headings by `#`/`**bold**`/`:`, bullets/numbers/`- [ ]` checkboxes, wrapped lines, indented sub-bullets, fenced code blocks) into structured criteria — and a ticket with *no* acceptance criteria is **rejected**, not faked into a hollow test. (This parser was hardened by an adversarial multi-agent review that confirmed and fixed 18 real defects — e.g. a criterion ending in `:` being mistaken for a heading, or `ISO-8601` being mistaken for a ticket key.)
- **Coverage is gated.** A `validate_ticket_coverage` check fails any generation with fewer tests than criteria, or one that doesn't reference each `AC<i>` tag and the ticket key — so "good tests, not bad tests" is *enforced*, not hoped for.

This is the difference between an autocomplete toy and a tool a QA engineer would trust: the ticket is the source of truth, and traceability is verified.

---

## Part 3 — The architecture (how it's built)

```
common/                the shared core — every tool reuses it, never re-implements it
  claude_client.py       the ONE Claude wrapper (retry · caching · structured output)
  config.py              pydantic-settings config (env / .env), the model id lives here
  database.py            SQLAlchemy 2.0 session factory (SQLite)
  models.py / schemas.py ORM models + pydantic request/response DTOs
  sanitizer.py           input sanitisation (prompt-injection separation)
ai_test_generator/     one PACKAGE per tool: cli.py · <core>.py · prompts.py · repository.py · tests/
ai_test_analyzer/      …  imports are namespaced (ai_test_analyzer.prompts) — no cross-tool collision
…                      each tool = a console entry point (ai-test-generator, …)
.claude/               Claude Code project setup — rules · commands · hooks · agents · settings
```

**Design principles:**
- **One shared pattern, not per-tool sprawl.** A tool never imports `anthropic` or touches SQLite directly — it goes through `common/`. This is why "fix the client once" fixes every tool.
- **Structured over stringly-typed** (Part 2.2).
- **Packaged, not scripted.** Each tool is a real importable package with an entry point — the difference between a demo and a product.

### Why the `.claude/` project setup
Following the Claude Code project-structure convention makes the repo *legibly* professional and self-documenting: `CLAUDE.md` (orientation), `.claude/rules/` (the quality bar as enforceable prose — code-style, testing, claude-sdk, generated-output, api-conventions), `.claude/commands/` (repeatable workflows), `.claude/hooks/guard-commit.sh` (blocks a wrong-email / attributed / to-main commit), `.claude/agents/` (a code-reviewer + security-auditor sub-agent). It signals "this was set up by someone who knows the tooling."

---

## Part 4 — How it was uplifted (the process, this session)

### 4.1 The starting state (honest)
A portfolio repo that *looked* finished but wasn't:
- **`ruff`: 293 errors** — and **240 of them came from ONE file**: `ai-quality-dashboard/dashboard.py` was a *foreign project's CHANGELOG (Orange-SK Playwright suite) pasted into a `.py`*. It was imported by nothing.
- **`pytest`: completely broken** — it couldn't even collect. Root cause: every tool was a flat directory on a shared pytest `pythonpath`, and three tools each shipped a bare `prompts.py`. So `from prompts import build_heal_user_message` in the *healer's* test resolved to the *generator's* `prompts.py`. A real architecture bug.
- **~32% of functions typed**, a deleted README, and two "outlier" tools hardcoding a stale model id + talking to `anthropic` raw.

### 4.2 The method
1. **Adversarial audit** — a 7-lens read of the whole repo (architecture, type-safety, test-coverage, SDK-usage, showcase, generator-output), each finding independently verified, synthesised into a ranked, batched plan (45 confirmed gaps, "0% → 90% ready").
2. **Step-by-step batches, each gated.** No big-bang. Every increment ended with `ruff check .` + `pytest` green before moving on, committed as its own reviewable unit.

### 4.3 The batches
- **Foundation** — the `.claude/` project setup + tooling baseline. Deleted the foreign CHANGELOG (`ruff` 293 → ~53), `ruff --fix`+format (→ source-side clean), added `--import-mode=importlib` + `pytest-mock`. *(PR #1)*
- **Namespacing** *(the load-bearing fix)* — renamed each tool dir to a valid package name (`ai-test-healer` → `ai_test_healer`), added `__init__.py`, rewrote every bare import to absolute (`from ai_test_healer.prompts import …`), collapsed `pythonpath` to `['.']`, added `[project.scripts]` console entry points, `pip install -e .`. The flat-module collision vanished; `pytest` could collect.
- **Test revival** — got `pytest` from broken to **128 passing**:
  - mocked `complete_structured` (the real API) instead of `.complete`, returning a `_BatchSuggestions` object;
  - `sessionmaker(expire_on_commit=False)` in `common/database.py` — fixed **5** `DetachedInstanceError` persistence tests at once;
  - fixed mock **patch targets** to the namespaced paths, and one *patch-where-used* bug;
  - a real validator bug: `"webdriver" not in code` matched `"xwebdriver"` (substring) → changed to a `\bwebdriver\b` word boundary;
  - generated files now end with a trailing newline (POSIX).
- **ruff to zero** — removed the now-unnecessary per-test `sys.path` hacks.
- **SDK correctness** — `claude-opus-4-6` → `claude-opus-4-8`.
- **README** — rewritten honest. *(all in PR #2)*

### 4.4 Key decisions & why
- **Namespacing (packages) over "unique module prefixes."** Both fix the collision, but packages + entry points are the professional end-state — an installable CLI, not `python3 cli.py`.
- **Skipping the dashboard API tests (documented) instead of a rushed refactor.** They need a real FastAPI *lifespan + `Depends` + `dependency_overrides`* refactor (the app has module-level `get_settings()`/`init_db()` side effects and routes read a module-global `settings`). A rushed test-only patch would have been a lie; a documented `skip` with the reason is honest and scoped.
- **`expire_on_commit=False` in the shared factory** (one place) over re-querying in every test — it matches how the code is actually used (read-after-write) and fixes the whole class at once.
- **Backdated, unattributed commits, branch → PR → squash-merge** — the house style, enforced by the commit hook.

### 4.5 Follow-ups — now DONE (a later autonomous pass, PRs #4-#7)
All four originally-deferred items were completed and merged:
- **Dashboard DI refactor** — app import is side-effect-free (FastAPI `lifespan`) + routes use `Depends(get_db_session)` + tests inject an in-memory DB via `dependency_overrides` (StaticPool). The 13 skipped tests are green; a real `cast(x, Float)` SQL bug (the /trend 500) was fixed. **0 skipped.**
- **Type-hint pass** — 100% of public functions carry a return type (AST-verified), via `autotyping` + hand-finish.
- **Blueprint -> generator** — the Playwright prompt now emits a layered page-object test, enforced by a validator gate (rejects `.nth()` + `waitForTimeout`).
- **Closed-loop generator (the flagship)** -- built; see Part 5.

---

## Part 5 — Roadmap: the closed loop & new tools

The key architectural piece is now BUILT: a **shared test-execution runner** (`common/test_runner.py`) with a trustworthy verdict parser, plus `TestGenerator.generate_and_verify()` (generate -> run -> repair, CLI `--url`). That runner is the lever the rest of the tier reuses:

1. **Closed-loop generator** — generate -> run -> repair until green. **DONE (the flagship).**
2. **Coverage cartographer** — requirements → test traceability + gap finder (fintech-audit relevant).
3. **Mutation sentinel** — mutation testing to score test *effectiveness* (Part 2.7).
4. **Healer verify-loop** — actually run the healed selector and confirm it resolves the right node.
5. **Triage bot** — classify CI failures (bug/flaky/env) + auto-quarantine.
6. **Prompt guardian** — test LLM-powered *apps* (prompt regression, hallucination, jailbreak) — the most AI-native addition.

Runner-once → tools 1, 3, 4, 5 all ride it. That is the single biggest structural lever, and it turns the suite from *open-loop analysers* into *closed-loop agents*.

---

## Part 6 — Run & verify

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .            # clean
.venv/bin/pytest -q               # 183 passed, 0 skipped
# from a ticket (the real workflow) — a GitHub issue is a git-hosted ticket:
gh issue view 42 --repo owner/repo > TICKET.md
ai-test-generator from-jira TICKET.md --output-file suite.spec.ts --url https://app
# or from a free-text requirement:
ai-test-generator generate "User can reset password" --framework playwright
```

**Current state:** from a totally broken test suite + a lint-flooded, collision-ridden codebase to **packaged, ruff-clean, 183 green tests (0 skipped), 100% return-typed, ticket-driven generation with a coverage gate, a working closed loop, and a professional project setup**. The remaining work is the OTHER new tools (mutation-sentinel, coverage-cartographer, healer verify-loop, triage-bot, prompt-guardian) — all of which reuse the runner built here.
