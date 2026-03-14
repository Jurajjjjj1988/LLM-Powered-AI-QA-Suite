"""
AI Data Mock-Architect — generátor syntetických GDPR-safe dát z OpenAPI schémy.

Agent pipeline (bežný terminál):
  1. schema-architect subagent: parsuje OpenAPI, identifikuje POST/PUT endpointy
  2. data-generator subagent: generuje 5 sád syntetických dát na endpoint
  3. security-auditor subagent: overí že dáta neobsahujú PII
  4. Orchestrátor: zapíše mocks/endpoints/<METHOD>_<slug>/data.json

Fallback (ak beží vnútri Claude Code session):
  - Priamy Anthropic API call s rovnakou logikou

Spúšťaj z terminálu mimo Claude Code:
  python3 cli.py generate swagger.json
  python3 cli.py generate https://petstore.swagger.io/v2/swagger.json
"""
from __future__ import annotations

import anyio
import json
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


ARCHITECT_PROMPT = _load_prompt("ARCHITECT.MD")
SDET_PROMPT = _load_prompt("SDET.MD")
SECURITY_PROMPT = _load_prompt("SECURITY.MD")

ORCHESTRATOR_PROMPT = """\
You are the lead orchestrator for AI Data Mock-Architect.

Your job:
1. Use the `schema-architect` subagent to parse the OpenAPI/Swagger spec and
   extract all POST and PUT endpoints with their request body schemas.
2. Use the `data-generator` subagent to generate exactly 5 synthetic mock data sets
   per endpoint. Data must be:
   - Semantically consistent (realistic-looking but clearly fictional)
   - 100% synthetic — NO real PII (no real names, emails, phones, addresses)
   - GDPR-safe (all values are obviously fabricated test data)
3. Use the `security-auditor` subagent to confirm no PII slipped through.
4. For each endpoint write mocks to:
   `mocks/endpoints/<HTTP_METHOD>_<path_slug>/data.json`
   where path_slug replaces / and { } with underscores.
5. Write `mocks/README.md` with a summary table of endpoints and mock counts.

JSON format for each data.json:
{
  "endpoint": "POST /users/register",
  "schema_summary": "...",
  "mocks": [ { ...mock 1... }, { ...mock 2... }, ... ]
}
"""

# ---------------------------------------------------------------------------
# Agent SDK pipeline (mimo Claude Code session)
# ---------------------------------------------------------------------------


async def _run_agent_pipeline(spec_source: str, cwd: str, api_key: str) -> str:
    from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition, ResultMessage

    is_url = spec_source.startswith("http://") or spec_source.startswith("https://")
    read_instruction = (
        f"Fetch the OpenAPI spec from URL: {spec_source}"
        if is_url
        else f"Read the OpenAPI spec from file: {spec_source}"
    )
    tools = ["WebFetch", "Write", "Agent"] if is_url else ["Read", "Write", "Agent"]

    prompt = (
        f"{read_instruction}\n\n"
        "Then:\n"
        "1. Use `schema-architect` to identify all POST/PUT endpoints + their schemas.\n"
        "2. Use `data-generator` to create 5 GDPR-safe synthetic mock sets per endpoint.\n"
        "3. Use `security-auditor` to confirm no real PII is present.\n"
        "4. Write each endpoint's mocks to `mocks/endpoints/<METHOD>_<slug>/data.json`.\n"
        "5. Write `mocks/README.md` with a summary table.\n"
        "6. Return: how many endpoints processed, how many mock files created."
    )

    result_text = ""
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            cwd=cwd,
            allowed_tools=tools,
            permission_mode="acceptEdits",
            model="claude-opus-4-6",
            system_prompt=ORCHESTRATOR_PROMPT,
            env={"ANTHROPIC_API_KEY": api_key},
            agents={
                "schema-architect": AgentDefinition(
                    description=(
                        "Lead Software Architect specialising in OpenAPI/Swagger. "
                        "Parses the spec and returns structured list of POST/PUT endpoints "
                        "with full request body schemas."
                    ),
                    prompt=ARCHITECT_PROMPT,
                    tools=["Read", "WebFetch"],
                ),
                "data-generator": AgentDefinition(
                    description=(
                        "Senior SDET specialising in synthetic test data. "
                        "Creates 5 semantically consistent, GDPR-safe mock data sets "
                        "per endpoint schema. No real PII — all values are fabricated."
                    ),
                    prompt=SDET_PROMPT,
                    tools=["Read"],
                ),
                "security-auditor": AgentDefinition(
                    description=(
                        "Security expert who audits generated mock data for PII leakage. "
                        "Flags real names, emails, phones, or addresses. Returns PASS or violations."
                    ),
                    prompt=SECURITY_PROMPT,
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


def _run_direct_api(spec_source: str, api_key: str) -> dict[str, str]:
    """
    Vráti dict {relativna_cesta: obsah_suboru} — volajúci ich zapíše na disk.
    """
    import anthropic

    is_url = spec_source.startswith("http://") or spec_source.startswith("https://")
    if is_url:
        import urllib.request
        with urllib.request.urlopen(spec_source, timeout=15) as resp:  # noqa: S310
            spec_content = resp.read().decode("utf-8")
    else:
        spec_content = Path(spec_source).read_text(encoding="utf-8")

    client = anthropic.Anthropic(api_key=api_key)

    system = (
        ARCHITECT_PROMPT + "\n\n" + SDET_PROMPT + "\n\n" + SECURITY_PROMPT + "\n\n"
        "You are now acting as Architect + SDET + Security auditor combined.\n"
        "Parse the OpenAPI spec, extract POST/PUT endpoints, generate 5 GDPR-safe "
        "synthetic mock data sets per endpoint, verify no PII, then return a JSON object "
        "where each key is the relative file path and each value is the file content string.\n"
        "Format: { \"mocks/endpoints/POST_users_register/data.json\": \"{...}\", "
        "\"mocks/README.md\": \"...\" }"
    )

    user = (
        f"OpenAPI spec:\n```json\n{spec_content[:12000]}\n```\n\n"
        "Return a JSON object with file paths as keys and file contents as values. "
        "Include data.json for each POST/PUT endpoint and mocks/README.md."
    )

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        final = stream.get_final_message()

    raw = next((b.text for b in final.content if b.type == "text"), "{}")

    # Strip markdown fences if present
    if raw.strip().startswith("```"):
        lines = raw.strip().splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract first { ... } block
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            return json.loads(raw[start:end + 1])
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate(spec_source: str, output_dir: str | None = None) -> str:
    """
    Generuje GDPR-safe mock dáta z OpenAPI schémy.
    Automaticky zvolí Agent SDK alebo priamy API podľa prostredia.
    Vracia cestu k mocks/ adresáru.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

    cwd = str(Path(output_dir or ".").resolve())
    Path(cwd).mkdir(parents=True, exist_ok=True)

    in_claude_session = bool(os.environ.get("CLAUDECODE"))

    if in_claude_session:
        logger.warning(
            "Detekovaná Claude Code session — používam priamy Anthropic API. "
            "Pre plný multi-agent pipeline spusti z terminálu mimo Claude."
        )
        files = _run_direct_api(spec_source, api_key)
        for rel_path, content in files.items():
            out = Path(cwd) / rel_path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                content if isinstance(content, str) else json.dumps(content, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Zapísaný súbor", extra={"path": str(out)})
    else:
        logger.info("Spúšťam Agent SDK pipeline (Architect + SDET + Security subagenti)")
        anyio.run(_run_agent_pipeline, spec_source, cwd, api_key)

    return str(Path(cwd) / "mocks")
