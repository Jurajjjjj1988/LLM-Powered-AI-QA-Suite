"""
Main FlakyAnalyzer orchestration class for ai-test-analyzer.

Orchestration flow:
  1. Accept list[TestLogEntry] (already normalised by log_parser)
  2. Aggregate per-test stats; apply flaky threshold
  3. Batch flaky tests (≤10) → Claude for AI suggestions (structured output)
  4. Persist FlakyTestRun + FlakyTestResult rows
  5. Return FlakyAnalysisResponse
"""
from __future__ import annotations

import logging
from collections import defaultdict

from pydantic import BaseModel

from common.claude_client import ClaudeClient
from common.config import Settings, get_settings
from common.database import get_session, init_db
from common.exceptions import ClaudeAPIError
from common.schemas import (
    FlakyAnalysisRequest,
    FlakyAnalysisResponse,
    FlakyTestDetail,
    TestLogEntry,
)

from prompts import SYSTEM_PROMPT, build_batch_user_message
from repository import save_flaky_run


# ---------------------------------------------------------------------------
# Structured output schemas for Claude's batch analysis response
# ---------------------------------------------------------------------------

class _TestSuggestion(BaseModel):
    test_name: str
    root_cause: str
    fixes: list[str]


class _BatchSuggestions(BaseModel):
    suggestions: list[_TestSuggestion]


logger = logging.getLogger(__name__)

_BATCH_SIZE = 10  # max tests per Claude call (model context + cost control)


class FlakyAnalyzer:
    """
    Orchestrates flakiness detection and AI root-cause analysis.

    Why batch instead of per-test calls?
    - One Claude call for ≤10 tests vs. up to 10 individual calls → ~90% fewer
      API round-trips, lower latency, lower cost.
    - Structured output guarantees a valid, schema-matched response every time.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ClaudeClient(self._settings)
        init_db(self._settings.db_path)
        logger.info(
            "FlakyAnalyzer initialised",
            extra={"model": self._settings.claude_model},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, request: FlakyAnalysisRequest) -> FlakyAnalysisResponse:
        """
        Analyse the provided test log entries for flakiness.

        Returns FlakyAnalysisResponse containing a run_id, the list of flaky
        tests with AI suggestions, and the total number of distinct tests seen.
        """
        # 1. Aggregate stats per test name
        stats = _aggregate_stats(request.logs)
        total_tests = len(stats)

        # 2. Filter flaky tests by threshold
        threshold = self._settings.analyzer_flaky_threshold_percent
        flaky_stats = {
            name: s for name, s in stats.items() if s["fail_rate"] >= threshold
        }
        logger.info(
            "Flaky test detection complete",
            extra={
                "total_tests": total_tests,
                "flaky_count": len(flaky_stats),
                "threshold_pct": threshold,
            },
        )

        # 3. AI analysis in batches
        flaky_details = self._enrich_with_ai(flaky_stats)

        # 4. Persist
        with get_session(self._settings.db_path) as session:
            run = save_flaky_run(
                session,
                source_file=request.source_file,
                total_tests=total_tests,
                flaky_count=len(flaky_details),
                results=flaky_details,
                model_used=self._settings.claude_model if flaky_details else None,
            )
            run_id = run.id

        return FlakyAnalysisResponse(
            run_id=run_id,
            flaky_tests=flaky_details,
            total_analyzed=total_tests,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enrich_with_ai(self, flaky_stats: dict[str, dict]) -> list[FlakyTestDetail]:
        """
        Split flaky tests into batches of ≤10, call Claude once per batch using
        structured outputs, and return FlakyTestDetail objects.

        Falls back gracefully: if the batch call fails, details are saved without
        AI suggestions rather than raising.
        """
        if not flaky_stats:
            return []

        items = [
            {
                "test_name": name,
                "fail_rate": round(s["fail_rate"], 2),
                "total_runs": s["total_runs"],
                "avg_duration_seconds": round(s["avg_duration"], 4),
            }
            for name, s in flaky_stats.items()
        ]

        # Build a lookup from test_name → suggestion for positional-safe matching
        suggestion_map: dict[str, _TestSuggestion] = {}
        for batch_start in range(0, len(items), _BATCH_SIZE):
            batch = items[batch_start : batch_start + _BATCH_SIZE]
            batch_suggestions = self._get_ai_suggestions(batch)
            for s in batch_suggestions:
                suggestion_map[s.test_name] = s

        results: list[FlakyTestDetail] = []
        for item in items:
            suggestion_text: str | None = None
            s = suggestion_map.get(item["test_name"])
            if s and (s.root_cause or s.fixes):
                fix_lines = "\n".join(f"  {i+1}. {f}" for i, f in enumerate(s.fixes))
                suggestion_text = f"Root cause: {s.root_cause}\nFixes:\n{fix_lines}".strip()

            results.append(
                FlakyTestDetail(
                    test_name=item["test_name"],
                    fail_rate=item["fail_rate"],
                    total_runs=item["total_runs"],
                    avg_duration_seconds=item["avg_duration_seconds"],
                    ai_suggestion=suggestion_text,
                )
            )
        return results

    def _get_ai_suggestions(self, batch: list[dict]) -> list[_TestSuggestion]:
        """
        Call Claude with a batch of flaky test stats using structured outputs.
        Returns a list of _TestSuggestion objects.
        Falls back to an empty list on any failure so callers degrade gracefully.
        """
        user_message = build_batch_user_message(batch)
        try:
            result, tokens = self._client.complete_structured(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_message,
                output_schema=_BatchSuggestions,
                max_tokens=self._settings.claude_max_tokens,
            )
        except ClaudeAPIError:
            logger.exception(
                "Claude API call failed for flaky batch analysis",
                extra={"batch_size": len(batch)},
            )
            return []

        logger.debug(
            "Claude structured batch analysis complete",
            extra={"batch_size": len(batch), "tokens": tokens, "suggestions": len(result.suggestions)},
        )
        return result.suggestions


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _aggregate_stats(entries: list[TestLogEntry]) -> dict[str, dict]:
    """
    Aggregate TestLogEntry list into per-test stats dicts:
      {test_name: {fail_rate, total_runs, avg_duration}}
    """
    buckets: dict[str, dict] = defaultdict(
        lambda: {"pass": 0, "fail": 0, "skip": 0, "durations": []}
    )

    for entry in entries:
        b = buckets[entry.test]
        b["durations"].append(entry.duration)
        normalized = entry.status.upper()
        if normalized == "PASS":
            b["pass"] += 1
        elif normalized == "FAIL":
            b["fail"] += 1
        else:
            b["skip"] += 1

    stats: dict[str, dict] = {}
    for name, b in buckets.items():
        total = b["pass"] + b["fail"]  # skips excluded from flaky calc
        fail_rate = (b["fail"] / total * 100) if total > 0 else 0.0
        avg_duration = sum(b["durations"]) / len(b["durations"]) if b["durations"] else 0.0
        stats[name] = {
            "fail_rate": fail_rate,
            "total_runs": total,
            "avg_duration": avg_duration,
        }
    return stats
