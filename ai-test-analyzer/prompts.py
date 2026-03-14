"""
Prompt templates for ai-test-analyzer.

Batch design: one Claude call for up to 10 flaky tests.
Uses structured outputs (Pydantic schema) so the response is always valid
and no defensive JSON parsing is needed in the analyzer.

System prompt is STATIC — no user content ever enters it.
"""
from __future__ import annotations

import json

SYSTEM_PROMPT = """\
You are an expert QA engineer specialising in test flakiness root-cause analysis.
You receive a JSON array of flaky test statistics and return a structured diagnosis
for each test.

Your response MUST be a JSON object with a single key "suggestions" containing an
array of objects — one per input test, in the SAME ORDER as the input.

Each element must have exactly:
  {
    "test_name": "<string — copy from input>",
    "root_cause": "<1-2 sentence diagnosis>",
    "fixes": ["<fix 1>", "<fix 2>", "<fix 3>"]
  }

If you cannot diagnose a test, set root_cause to "Unknown" and fixes to
["Investigate test isolation", "Add explicit waits", "Check for shared state"].
"""


def build_batch_user_message(flaky_tests: list[dict]) -> str:
    """
    Build the user-turn message for a batch of up to 10 flaky test dicts.

    Each dict must have: test_name, fail_rate, total_runs, avg_duration_seconds.
    User data goes here (user turn), never in the system prompt.
    """
    batch = flaky_tests[:10]
    payload = json.dumps(batch, indent=2)
    return (
        "Analyse the following flaky test statistics and return your structured diagnosis.\n\n"
        f"Input:\n{payload}"
    )
