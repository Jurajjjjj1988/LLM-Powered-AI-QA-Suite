"""
Validator for AI-generated test code.

Validates that the generated output contains the structural markers expected
for each supported framework. Deliberately lightweight — deep AST parsing is
out of scope; the goal is catching empty or hallucinated non-code responses
before they hit disk or the database.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Minimum number of `test(` or `it(` call sites to accept the output
_MIN_TEST_CALLS = 1


class ValidationResult:
    __slots__ = ("passed", "reasons")

    def __init__(self, passed: bool, reasons: list[str]) -> None:
        self.passed = passed
        self.reasons = reasons

    def __bool__(self) -> bool:
        return self.passed

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"ValidationResult({status}, reasons={self.reasons!r})"


# ---------------------------------------------------------------------------
# Framework-specific rule sets
# ---------------------------------------------------------------------------


def _validate_playwright(code: str) -> ValidationResult:
    reasons: list[str] = []

    # Must import test + expect from @playwright/test (any extra named imports allowed,
    # e.g. `type Page, type Locator` for the page-object style).
    if not re.search(
        r"import\s*\{[^}]*\btest\b[^}]*\bexpect\b[^}]*\}\s*from\s*['\"]@playwright/test['\"]",
        code,
    ):
        reasons.append("Missing `import { test, expect } from '@playwright/test'`")

    # Count test( call-sites (handles `test(` and `test.only(` / `test.skip(`)
    test_calls = len(re.findall(r"\btest\s*\(", code))
    if test_calls < _MIN_TEST_CALLS:
        reasons.append(f"Expected at least {_MIN_TEST_CALLS} `test(` call(s), found {test_calls}")

    # Must have at least one expect assertion
    if "expect(" not in code:
        reasons.append("No `expect(` assertion found")

    # layered-playwright-suite bar: stable selectors + web-first assertions only.
    if ".nth(" in code:
        reasons.append("Positional locator `.nth()` — use a semantic/stable locator instead")
    if "waitForTimeout" in code:
        reasons.append("Hard wait `waitForTimeout` — use a web-first assertion instead")

    return ValidationResult(passed=len(reasons) == 0, reasons=reasons)


def _validate_cypress(code: str) -> ValidationResult:
    reasons: list[str] = []

    # Cypress tests use describe + it (or cy.* at minimum)
    has_describe = bool(re.search(r"\bdescribe\s*\(", code))
    has_it = bool(re.search(r"\bit\s*\(", code))
    has_cy = "cy." in code

    if not has_describe:
        reasons.append("No `describe(` block found")
    if not has_it:
        reasons.append(f"Expected at least {_MIN_TEST_CALLS} `it(` call(s), found 0")
    if not has_cy:
        reasons.append("No `cy.` Cypress command usage found")

    return ValidationResult(passed=len(reasons) == 0, reasons=reasons)


def _validate_selenium(code: str) -> ValidationResult:
    reasons: list[str] = []

    if "import pytest" not in code:
        reasons.append("Missing `import pytest`")

    if not re.search(r"\bwebdriver\b", code):
        reasons.append("Missing selenium webdriver import or usage")

    test_fns = len(re.findall(r"def test_", code))
    if test_fns < _MIN_TEST_CALLS:
        reasons.append(
            f"Expected at least {_MIN_TEST_CALLS} `def test_` function(s), found {test_fns}"
        )

    return ValidationResult(passed=len(reasons) == 0, reasons=reasons)


_VALIDATORS = {
    "playwright": _validate_playwright,
    "cypress": _validate_cypress,
    "selenium": _validate_selenium,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_TEST_UNIT_PATTERN = {
    "playwright": r"\btest\s*\(",
    "cypress": r"\bit\s*\(",
    "selenium": r"def\s+test_",
}


def validate_ticket_coverage(
    code: str, framework: str, criteria_count: int, ticket_key: str
) -> ValidationResult:
    """Verify generated code actually covers a ticket: enough tests + traceable to the key.

    The "good tests, not bad tests" gate — one test per acceptance criterion. Fails if
    there are fewer test blocks than criteria, or the ticket key is absent (so a test
    can't be traced back to what it verifies).
    """
    reasons: list[str] = []
    pattern = _TEST_UNIT_PATTERN.get(framework.lower(), _TEST_UNIT_PATTERN["playwright"])
    test_count = len(re.findall(pattern, code))
    if test_count < criteria_count:
        reasons.append(
            f"Only {test_count} test(s) for {criteria_count} acceptance criteria — "
            "expected at least one test per criterion"
        )

    # Per-criterion traceability: each AC<i> tag must actually appear (not just a count).
    missing = [f"AC{i}" for i in range(1, criteria_count + 1) if not re.search(rf"\bAC{i}\b", code)]
    if missing:
        shown = ", ".join(missing[:5]) + ("…" if len(missing) > 5 else "")
        reasons.append(f"Missing per-criterion traceability tag(s): {shown}")

    # Key must appear as a whole token (so 'AB-1' does not match inside 'AB-12').
    if not re.search(rf"(?<![A-Za-z0-9]){re.escape(ticket_key)}(?![A-Za-z0-9])", code):
        reasons.append(f"Ticket key {ticket_key!r} not referenced — tests are not traceable")
    return ValidationResult(passed=len(reasons) == 0, reasons=reasons)


def validate_generated_code(code: str, framework: str) -> ValidationResult:
    """
    Validate that *code* looks like a valid test file for *framework*.

    Returns a ValidationResult; callers should inspect `.passed` and `.reasons`.
    Never raises — validation failures are represented in the result object so
    callers can decide whether to persist anyway (with validation_passed=False).
    """
    if not code or not code.strip():
        return ValidationResult(passed=False, reasons=["Generated code is empty"])

    fn = _VALIDATORS.get(framework.lower())
    if fn is None:
        supported = ", ".join(_VALIDATORS)
        logger.warning(
            "Unknown framework for validation, skipping structural checks",
            extra={"framework": framework, "supported": supported},
        )
        # Treat as passed with a warning so unknown frameworks are not blocked
        return ValidationResult(
            passed=True,
            reasons=[f"No validator for framework {framework!r}; skipped structural checks"],
        )

    result = fn(code)
    if result.passed:
        logger.debug(
            "Code validation passed",
            extra={"framework": framework, "code_length": len(code)},
        )
    else:
        logger.warning(
            "Code validation failed",
            extra={"framework": framework, "reasons": result.reasons},
        )
    return result
