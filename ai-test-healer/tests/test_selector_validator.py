"""
Test strategy for ai-test-healer / selector_validator.py
==========================================================
Coverage targets:
  1. Accepts common valid CSS selectors (class, id, attribute, pseudo, combinator).
  2. Rejects XPath expressions (strings starting with / or //).
  3. Rejects empty string and whitespace-only input.
  4. Rejects selectors longer than 512 characters (cssselect will parse them but
     the healer guards against them — this test verifies cssselect's behaviour
     with extreme input is handled gracefully and returns a result not exception).
  5. Rejects the literal string "NONE".
  6. SelectorValidationResult bool protocol works.
  7. Never raises — all failures represented in result.valid / result.reason.

Pure unit tests — no DB, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOL_ROOT = Path(__file__).parent.parent
REPO_ROOT = TOOL_ROOT.parent

for p in (str(TOOL_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from selector_validator import SelectorValidationResult, validate_css_selector


# ---------------------------------------------------------------------------
# Valid selectors
# ---------------------------------------------------------------------------

class TestValidCssSelectors:
    @pytest.mark.parametrize("selector", [
        "button",
        ".submit-btn",
        "#login-form",
        "div > span",
        "input[type='email']",
        "ul li:first-child",
        "a.nav-link:hover",
        "form button.btn-primary",
        "[data-testid='submit']",
        "div.container > .row:nth-child(2)",
    ])
    def test_should_accept_valid_css_selector(self, selector):
        result = validate_css_selector(selector)
        assert result.valid is True
        assert result.reason == ""

    def test_should_return_true_for_bool_on_valid_selector(self):
        result = validate_css_selector("button.submit")
        assert bool(result) is True


# ---------------------------------------------------------------------------
# XPath rejection
# ---------------------------------------------------------------------------

class TestXPathRejection:
    @pytest.mark.parametrize("xpath", [
        "//div[@class='submit']",
        "/html/body/button",
        "//input[@type='text']",
    ])
    def test_should_reject_xpath_expression(self, xpath):
        result = validate_css_selector(xpath)
        assert result.valid is False
        assert "xpath" in result.reason.lower() or "css" in result.reason.lower()


# ---------------------------------------------------------------------------
# Empty and whitespace
# ---------------------------------------------------------------------------

class TestEmptyAndWhitespace:
    def test_should_reject_empty_string(self):
        result = validate_css_selector("")
        assert result.valid is False
        assert "empty" in result.reason.lower()

    def test_should_reject_whitespace_only_string(self):
        result = validate_css_selector("   \t\n  ")
        assert result.valid is False

    def test_should_reject_none_literal_string(self):
        result = validate_css_selector("NONE")
        assert result.valid is False
        assert "none" in result.reason.lower()

    def test_should_reject_none_lowercase(self):
        result = validate_css_selector("none")
        assert result.valid is False


# ---------------------------------------------------------------------------
# Very long selectors
# ---------------------------------------------------------------------------

class TestLongSelectors:
    def test_should_handle_512_char_selector_without_raising(self):
        """512-char selector — validate_css_selector must not raise."""
        selector = "div." + "a" * 507  # 512 total
        result = validate_css_selector(selector)
        # Result may be valid or invalid but must never raise
        assert isinstance(result, SelectorValidationResult)

    def test_should_handle_extreme_length_selector_without_raising(self):
        """Extreme length — must not raise regardless of cssselect internals."""
        selector = "div." + "x" * 2000
        try:
            result = validate_css_selector(selector)
            assert isinstance(result, SelectorValidationResult)
        except Exception as exc:
            pytest.fail(f"validate_css_selector raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# SelectorValidationResult protocol
# ---------------------------------------------------------------------------

class TestSelectorValidationResult:
    def test_should_bool_false_when_valid_is_false(self):
        r = SelectorValidationResult(valid=False, reason="bad")
        assert bool(r) is False

    def test_should_bool_true_when_valid_is_true(self):
        r = SelectorValidationResult(valid=True)
        assert bool(r) is True

    def test_should_repr_include_valid_and_reason(self):
        r = SelectorValidationResult(valid=False, reason="XPath")
        assert "False" in repr(r)
        assert "XPath" in repr(r)

    def test_should_default_reason_to_empty_string(self):
        r = SelectorValidationResult(valid=True)
        assert r.reason == ""


# ---------------------------------------------------------------------------
# Never-raise contract
# ---------------------------------------------------------------------------

class TestNeverRaiseContract:
    @pytest.mark.parametrize("selector", [
        "",
        "NONE",
        "//xpath",
        "???!!!",
        "\x00\x01",
        "a" * 10000,
        "::invalid-pseudo",
    ])
    def test_should_never_raise_exception_for_any_input(self, selector):
        """validate_css_selector must return a result, never raise."""
        try:
            result = validate_css_selector(selector)
            assert isinstance(result, SelectorValidationResult)
        except Exception as exc:
            pytest.fail(
                f"validate_css_selector raised for input {selector!r}: {exc}"
            )
