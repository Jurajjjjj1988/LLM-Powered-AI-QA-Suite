# AI Debug-Accelerator

Skráti MTTR (Mean Time To Resolution) pri Playwright zlyhaní. Analyzuje test report, identifikuje root cause každého failu a generuje akčný markdown report s konkretnými code fixmi.

---

## Ako to funguje

```
Playwright JSON report
        │
        ▼
 SDET subagent          ← identifikuje root cause, navrhuje Playwright fix code
        │
        ▼
 Code Review subagent   ← validuje fixy, hodnotí kvalitu (Criticality Score 1-10)
        │
        ▼
 ai_debug_report.md     ← summary tabuľka + detaily + OWASP security tipy
```

**Agent SDK pipeline** (spustenie z terminálu mimo Claude Code):
- `sdet-analyzer` subagent — Senior SDET, Playwright špecialista
- `code-reviewer` subagent — Senior Code Reviewer

**Fallback** (keď beží vnorene v Claude Code session):
- Priamy Anthropic API s kombinovaným SDET + Code Review promptom

---

## Inštalácia

```bash
pip3 install anthropic claude-agent-sdk click python-dotenv anyio
```

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-api03-...
```

---

## Použitie

```bash
# Základné použitie
python3 cli.py analyze playwright-report.json

# Ulož report do konkrétneho adresára
python3 cli.py analyze results/report.json --output-dir ./debug-reports

# Otvor report po vygenerovaní
python3 cli.py analyze playwright-report.json --open
```

---

## Formát vstupného reportu

Nástroj akceptuje **Playwright JSON reporter** výstup:

```bash
# playwright.config.ts
reporter: [['json', { outputFile: 'playwright-report.json' }]]
```

Príklad spustenia testov:
```bash
npx playwright test --reporter=json > playwright-report.json
```

Pozri `sample-report.json` pre príklad formátu.

---

## Výstup — `ai_debug_report.md`

Report obsahuje:

| Sekcia | Obsah |
|---|---|
| **Executive Summary** | Tabuľka: Test Name \| Root Cause \| Fix Summary |
| **Details** | Jedna podsekcia per fail — root cause analýza + Before/After code |
| **Criticality Scores** | Hodnotenie každého problému 1–10 |
| **OWASP Security Flags** | Bezpečnostné riziká odhalené pri analýze |
| **TODO list** | Čo ešte treba overiť alebo pokryť testami |
| **Cross-Cutting Recommendations** | `playwright.config.ts` nastavenia pre CI stabilitu |

---

## Agent Prompty

Nástroj používa tieto agent prompty z `/ai-agents/prompts/`:

| Agent | Prompt súbor | Rola |
|---|---|---|
| `sdet-analyzer` | `SDET.MD` | Root cause analýza, Playwright fix code |
| `code-reviewer` | `CODE_REVIEW.MD` | Validácia fixov, Before/After snippety |

---

## Príklad výstupu

```markdown
## 1. Executive Summary

| # | Test Name | Root Cause | Fix Summary |
|---|-----------|------------|-------------|
| 1 | should redirect to dashboard | Submit button hidden — client-side validation gate | Wait for toBeVisible() + toBeEnabled() before click |
| 2 | should show error on invalid creds | Missing waitForResponse() before assertion | Gate assertion on 401 API response |
| 3 | should complete purchase | Race condition — asserts during "Processing..." state | waitForURL('**/confirmation**') before verify |

## 2. Details
### 2.1 ❌ should redirect to dashboard
...konkrétny Playwright TypeScript fix...
```

---

## Multi-Agent Pipeline (mimo Claude Code)

Pre plný pipeline s dvoma subagentmi spusti z terminálu priamo (nie cez Claude Code):

```bash
# Otvor nový terminál
cd ~/ai-qa-projects/ai-debug-accelerator
python3 cli.py analyze playwright-report.json
```

Claude Code session detekuje premenná `CLAUDECODE` — ak je nastavená, automaticky fallbackuje na priamy API.
