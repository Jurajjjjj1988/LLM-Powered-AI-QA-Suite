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

    # Must import the test runner
    if "import { test, expect }" not in code and "import {test, expect}" not in code:
        reasons.append(
            "Missing `import { test, expect } from '@playwright/test'`"
        )

    # Count test( call-sites (handles `test(` and `test.only(` / `test.skip(`)
    test_calls = len(re.findall(r"\btest\s*\(", code))
    if test_calls < _MIN_TEST_CALLS:
        reasons.append(
            f"Expected at least {_MIN_TEST_CALLS} `test(` call(s), found {test_calls}"
        )

    # Must have at least one expect assertion
    if "expect(" not in code:
        reasons.append("No `expect(` assertion found")

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
        reasons.append(
            f"Expected at least {_MIN_TEST_CALLS} `it(` call(s), found 0"
        )
    if not has_cy:
        reasons.append("No `cy.` Cypress command usage found")

    return ValidationResult(passed=len(reasons) == 0, reasons=reasons)


def _validate_selenium(code: str) -> ValidationResult:
    reasons: list[str] = []

    if "import pytest" not in code:
        reasons.append("Missing `import pytest`")

    if "webdriver" not in code:
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
