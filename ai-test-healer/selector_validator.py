"""
CSS selector validator for ai-test-healer.

Uses the `cssselect` library (which in turn uses `lxml`'s parser) to verify
that a candidate selector is syntactically valid CSS.  We deliberately do NOT
run the selector against the live DOM — that would couple the validator to a
browser runtime.  Syntactic validity is sufficient to guard against model
hallucinations such as XPath expressions, plain words, or malformed output.

Why cssselect and not a regex?
- CSS selector grammar is complex (pseudo-elements, attribute combinators,
  :not(), :has(), etc.).  A regex allowlist would be brittle and
  over-restrictive.  cssselect uses a full grammar and raises
  `cssselect.SelectorSyntaxError` on invalid input.
"""
from __future__ import annotations

import logging

import cssselect

logger = logging.getLogger(__name__)


class SelectorValidationResult:
    __slots__ = ("valid", "reason")

    def __init__(self, valid: bool, reason: str = "") -> None:
        self.valid = valid
        self.reason = reason

    def __bool__(self) -> bool:
        return self.valid

    def __repr__(self) -> str:
        return f"SelectorValidationResult(valid={self.valid}, reason={self.reason!r})"


def validate_css_selector(selector: str) -> SelectorValidationResult:
    """
    Return a SelectorValidationResult indicating whether *selector* is
    syntactically valid CSS.

    Never raises — validation errors are represented in the result so the
    caller can decide to persist with validation_passed=False rather than
    aborting the workflow.
    """
    if not selector or not selector.strip():
        return SelectorValidationResult(valid=False, reason="Selector is empty")

    stripped = selector.strip()

    # Guard: model sometimes returns "NONE" even after we told it to
    if stripped.upper() == "NONE":
        return SelectorValidationResult(
            valid=False, reason="Model returned NONE — no selector found"
        )

    # Guard: reject obvious non-CSS patterns (XPath, plain sentences)
    if stripped.startswith("/") or stripped.startswith("//"):
        return SelectorValidationResult(
            valid=False, reason="Looks like an XPath expression, not a CSS selector"
        )

    try:
        parsed = cssselect.parse(stripped)
        if not parsed:
            return SelectorValidationResult(
                valid=False, reason="cssselect returned empty parse result"
            )
        logger.debug(
            "CSS selector validated",
            extra={"selector": stripped, "specificity": str(parsed[0].specificity())},
        )
        return SelectorValidationResult(valid=True)
    except cssselect.SelectorSyntaxError as exc:
        logger.warning(
            "CSS selector syntax error",
            extra={"selector": stripped, "error": str(exc)},
        )
        return SelectorValidationResult(
            valid=False, reason=f"SelectorSyntaxError: {exc}"
        )
    except Exception as exc:
        # cssselect can occasionally raise other exceptions on extreme inputs
        logger.warning(
            "Unexpected error during CSS selector validation",
            extra={"selector": stripped, "error": str(exc)},
        )
        return SelectorValidationResult(
            valid=False, reason=f"Unexpected validation error: {exc}"
        )
