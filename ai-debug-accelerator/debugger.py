"""
AI Debug-Accelerator — skráti MTTR (Mean Time To Resolution) pri Playwright zlyhaní.

Agent pipeline (bežný terminál):
  1. SDET subagent: analyzuje každý fail — root cause + fix
  2. Code Review subagent: validuje navrhnuté fixy
  3. Orchestrátor: zapíše ai_debug_report.md

Fallback (ak beží vnútri Claude Code session):
  - Priamy Anthropic API call s rovnakou logikou

Spúšťaj z terminálu mimo Claude Code:
  python3 cli.py analyze sample-report.json
"""
from __future__ import annotations

import anyio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Načítanie agent promptov
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path("/Users/kapusansky/ai-agents/prompts")


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    return path.read_text(encoding="utf-8") if path.exists() else ""


SDET_PROMPT = _load_prompt("SDET.MD")
CODE_REVIEW_PROMPT = _load_prompt("CODE_REVIEW.MD")

ORCHESTRATOR_PROMPT = """\
You are the lead QA orchestrator for the AI Debug-Accelerator.

Your job:
1. Use the `sdet-analyzer` subagent to analyse each failing test from the report file.
2. Use the `code-reviewer` subagent to validate the proposed fixes.
3. Compile all findings into a single markdown report and save it as `ai_debug_report.md`.

The report MUST contain:
- A summary table: | Test Name | Status | Root Cause | Fix Summary |
- A ## Details section with one subsection per failing test:
  - ### What happened (1-2 sentences)
  - ### Proposed fix (code snippet or steps)
  - ### Reviewer notes (from code-reviewer)

Be concise and actionable. No fluff.
"""

# ---------------------------------------------------------------------------
# Agent SDK pipeline (mimo Claude Code session)
# ---------------------------------------------------------------------------


async def _run_agent_pipeline(report_path: str, cwd: str, api_key: str) -> str:
    from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition, ResultMessage

    prompt = (
        f"Analyse the Playwright test report at: `{report_path}`\n\n"
        "1. Read the file — extract all FAILED tests with error messages and stack traces.\n"
        "2. Use the `sdet-analyzer` agent to diagnose each failure.\n"
        "3. Use the `code-reviewer` agent to validate the fixes.\n"
        "4. Write the complete markdown report to `ai_debug_report.md`.\n"
        "5. Return a short summary of findings."
    )

    result_text = ""
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            cwd=cwd,
            allowed_tools=["Read", "Glob", "Write", "Agent"],
            permission_mode="acceptEdits",
            model="claude-opus-4-6",
            system_prompt=ORCHESTRATOR_PROMPT,
            env={"ANTHROPIC_API_KEY": api_key},
            agents={
                "sdet-analyzer": AgentDefinition(
                    description=(
                        "Senior SDET specialising in Playwright test failure analysis. "
                        "Identifies root causes (timing, selector, assertion, network) "
                        "and provides concrete TypeScript/Playwright fix code."
                    ),
                    prompt=SDET_PROMPT,
                    tools=["Read", "Glob"],
                ),
                "code-reviewer": AgentDefinition(
                    description=(
                        "Senior code reviewer who validates proposed fixes for correctness, "
                        "readability, and adherence to Playwright best practices."
                    ),
                    prompt=CODE_REVIEW_PROMPT,
                    tools=["Read"],
                ),
            },
        ),
    ):
        if isinstance(message, ResultMessage):
            result_text = message.result

    return result_text


# ---------------------------------------------------------------------------
# Fallback: priamy Anthropic API (keď sme vnorení v Claude Code)
# ---------------------------------------------------------------------------


def _run_direct_api(report_path: str, api_key: str) -> str:
    import anthropic

    report_content = Path(report_path).read_text(encoding="utf-8")

    client = anthropic.Anthropic(api_key=api_key)

    system = (
        SDET_PROMPT + "\n\n" + CODE_REVIEW_PROMPT + "\n\n"
        "You are now acting as both SDET analyst and code reviewer combined.\n"
        "Analyse the Playwright test report JSON, identify root causes for each FAILED test, "
        "propose concrete fixes, then write a markdown report.\n"
        "Return ONLY the full markdown content of ai_debug_report.md."
    )

    user = (
        f"Playwright test report:\n```json\n{report_content}\n```\n\n"
        "Generate the complete ai_debug_report.md with:\n"
        "1. Summary table: | Test Name | Root Cause | Fix Summary |\n"
        "2. ## Details section — one subsection per failed test with root cause + fix code"
    )

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        final = stream.get_final_message()

    return next(
        (block.text for block in final.content if block.type == "text"), ""
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze(report_path: str, output_dir: str | None = None) -> str:
    """
    Analysuje Playwright report a zapíše ai_debug_report.md.
    Automaticky zvolí Agent SDK alebo priamy API podľa prostredia.
    Vracia cestu k vygenerovanému reportu.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

    report = Path(report_path).resolve()
    if not report.exists():
        raise FileNotFoundError(f"Report not found: {report}")

    cwd = str(Path(output_dir or report.parent).resolve())
    Path(cwd).mkdir(parents=True, exist_ok=True)

    # Detekuj či sme vnorení v Claude Code session
    in_claude_session = bool(os.environ.get("CLAUDECODE"))

    if in_claude_session:
        logger.warning(
            "Detekovaná Claude Code session — používam priamy Anthropic API (Agent SDK "
            "nemôže bežať vnorene). Pre plný multi-agent pipeline spusti z terminálu mimo Claude."
        )
        report_md = _run_direct_api(str(report), api_key)
    else:
        logger.info("Spúšťam Agent SDK pipeline (SDET + Code Review subagenti)")
        report_md = anyio.run(_run_agent_pipeline, str(report), cwd, api_key)

    output_path = Path(cwd) / "ai_debug_report.md"
    output_path.write_text(report_md, encoding="utf-8")
    logger.info("Report uložený", extra={"path": str(output_path)})

    return str(output_path)
