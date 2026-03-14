# LLM-Powered AI QA Suite

A production-ready suite of AI-powered QA tools built on top of the **Claude API (Opus 4.6)**. Each tool solves a real problem in automated testing pipelines — generating tests, detecting flaky tests, healing broken selectors, and visualising quality metrics.

---

## Tools

### `ai-test-generator`
Generates Playwright, Cypress, or Selenium test code from plain-English requirements.

```bash
cd ai-test-generator
python3 cli.py generate "User can log in with valid credentials" --framework playwright
```

- Claude Opus 4.6 with adaptive thinking
- Result caching by requirement hash (no duplicate API calls)
- Structural code validation before persisting to DB
- Supports `--output-file` to write directly to `.spec.ts`

---

### `ai-test-analyzer`
Detects flaky tests from test logs and provides AI root-cause analysis with fix suggestions.

```bash
cd ai-test-analyzer
cat test_results.json | python3 cli.py analyze -
```

- Batches up to 10 tests per Claude call (cost-efficient)
- **Structured outputs** via Pydantic schema — guaranteed valid response, no fragile JSON parsing
- Persists runs + per-test AI suggestions to SQLite DB

---

### `ai-test-healer`
Repairs broken CSS selectors using Claude. Ideal for self-healing Playwright/Cypress test suites.

```bash
cd ai-test-healer
python3 cli.py heal "Login button" "button.login" "<button class='btn-submit'>Login</button>"
```

- Cache: same broken selector + same HTML → zero API calls
- CSS syntax validation via `cssselect`
- Prefers stable attributes (`data-testid`, `aria-*`, `id`) over positional selectors

---

### `ai-quality-dashboard`
Read-only FastAPI dashboard exposing metrics from all three tools via REST API.

```bash
cd ai-quality-dashboard
python3 app.py
# → http://127.0.0.1:8000
# → http://127.0.0.1:8000/api/docs
```

**Endpoints:**
| Route | Description |
|---|---|
| `GET /api/metrics/summary` | Aggregate counts + avg flaky rate |
| `GET /api/generated-tests` | Paginated list of generated tests |
| `GET /api/flaky-tests` | Flaky analysis runs with AI suggestions |
| `GET /api/flaky-tests/trend` | Daily flaky-rate time series (last 30 days) |
| `GET /api/healed-selectors` | Healed CSS selector history |

---

## Architecture

```
ai-qa-projects/
├── common/                  # Shared across all tools
│   ├── claude_client.py     # Anthropic SDK wrapper (streaming, adaptive thinking, retries)
│   ├── config.py            # Pydantic Settings (reads from .env)
│   ├── database.py          # SQLAlchemy engine + session context managers
│   ├── models.py            # ORM models (GeneratedTest, FlakyTestRun, HealedSelector)
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── sanitizer.py         # Input validation and SHA-256 hashing
│   └── exceptions.py        # Typed exception hierarchy
├── ai-test-generator/
├── ai-test-analyzer/
├── ai-test-healer/
├── ai-quality-dashboard/
└── pyproject.toml
```

**Shared SQLite DB** at `~/ai-qa-projects/qa_suite.db` — all tools read/write the same database.

---

## Setup

```bash
# 1. Install dependencies
pip3 install anthropic python-dotenv pydantic-settings sqlalchemy tenacity cssselect fastapi uvicorn click

# 2. Create .env in each tool folder (or project root)
echo "ANTHROPIC_API_KEY=sk-ant-api03-..." > ai-test-generator/.env
# repeat for ai-test-analyzer, ai-test-healer, ai-quality-dashboard

# 3. Run any tool
cd ai-test-generator
python3 cli.py generate "..." --framework playwright
```

---

## Key Design Decisions

| Decision | Why |
|---|---|
| **Claude Opus 4.6** | Best reasoning for code generation and root-cause analysis |
| **Adaptive thinking** | Model decides when to think deeply — better quality, no wasted tokens |
| **Streaming for large outputs** | Prevents HTTP timeouts on 4096-token responses |
| **Structured outputs (Pydantic)** | Guaranteed valid schema from Claude — no JSON parsing edge cases |
| **Prompt injection separation** | User content always in the `user` turn, never in `system` prompt |
| **Result caching** | SHA-256 hash of input → skip Claude if result already in DB |
| **Read-only dashboard sessions** | `PRAGMA query_only = ON` per session — dashboard cannot corrupt data |

---

## Security

- API key validated against `sk-ant-api##-<90+ chars>` pattern on startup
- HTML snippets and selectors sanitized before injection into prompts
- `.env` files listed in `.gitignore` — secrets never committed
- Dashboard uses read-only DB sessions

---

## Model

Built with [Claude Opus 4.6](https://anthropic.com) via the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).
