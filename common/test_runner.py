"""
Shared test-execution runner — the closed-loop primitive (generate → RUN → repair).

The suite's tools are otherwise open-loop: they emit code but never run it. This
module is the one reusable piece that closes the loop — it runs a generated
Playwright spec via ``npx playwright test`` and parses the pass/fail verdict, so a
caller (the generator's repair loop, a future mutation-sentinel, a healer verify
step) can accept a green result or feed a red one back to the model.

``parse_playwright_verdict`` is a pure function (unit-tested); ``run_playwright_test``
is the thin subprocess wrapper around it. Green requires a *real* tally — exit 0
AND ``passed >= 1`` AND zero failed/flaky/timed-out — the same false-green defence
proven in the sibling PWmodernizer closed loop (a bare "passed" substring or an
all-skipped run must NOT count as green).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunResult:
    """Outcome of running a spec: a trustworthy green plus the raw counts + output."""

    passed: bool
    passed_count: int
    failed_count: int
    output: str


def _count(pattern: str, text: str) -> int:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def parse_playwright_verdict(output: str, exit_code: int) -> RunResult:
    """Parse ``npx playwright test`` output into a trustworthy verdict.

    Green iff the process exited 0 AND the tally is genuinely clean: at least one
    passed test and zero failed / flaky / timed-out / interrupted. A run with only
    skipped tests, or a "passed" appearing in a test title, is NOT green.
    """
    passed = _count(r"(\d+)\s+passed", output)
    failed = _count(r"(\d+)\s+failed", output)
    flaky = _count(r"(\d+)\s+flaky", output)
    timed_out = _count(r"(\d+)\s+timed out", output) + _count(r"(\d+)\s+interrupted", output)
    not_green = failed + flaky + timed_out
    is_green = exit_code == 0 and passed >= 1 and not_green == 0
    return RunResult(
        passed=is_green,
        passed_count=passed,
        failed_count=not_green,
        output=output,
    )


def run_playwright_test(
    spec_path: Path,
    base_url: str,
    *,
    timeout_seconds: int = 120,
) -> RunResult:
    """Run *spec_path* against *base_url* and return the parsed verdict.

    Requires Node + Playwright installed. ``BASE_URL`` is exported so a spec using
    a configured baseURL runs against the caller's target. Raises nothing on a
    failing test — a red run is a RunResult with ``passed=False`` (the repair
    signal), not an exception.
    """
    proc = subprocess.run(
        ["npx", "playwright", "test", str(spec_path), "--reporter=line"],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env={**os.environ, "BASE_URL": base_url},
        check=False,
    )
    return parse_playwright_verdict(f"{proc.stdout}\n{proc.stderr}", proc.returncode)
