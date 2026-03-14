"""
Test strategy for ai-test-generator / validator.py
====================================================
Coverage targets:
  1. Playwright validator:
     - Rejects code missing `import { test, expect }`.
     - Rejects code with zero `test(` call sites.
     - Accepts well-formed Playwright TypeScript code.
  2. Cypress validator:
     - Rejects code missing describe/it/cy usage.
     - Accepts valid Cypress code.
  3. Selenium validator:
     - Rejects code missing `import pytest` or `webdriver`.
     - Accepts valid Selenium Python code.
  4. validate_generated_code():
     - Returns passed=False for empty/whitespace input.
     - Treats unknown framework as passed=True (with warning reason).
  5. sanitize_requirement():
     - Raises SanitizationError for text < 10 chars.
     - Raises SanitizationError for text > 5000 chars.
     - Accepts exactly 10-char text (boundary).
     - Strips control characters.

Pattern: AAA unit tests, no DB or network required.
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

from validator import validate_generated_code


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PLAYWRIGHT = (
    "import { test, expect } from '@playwright/test';\n"
    "test.describe('Login', () => {\n"
    "  test('loads homepage', async ({ page }) => {\n"
    "    await page.goto('https://example.com');\n"
    "    await expect(page).toHaveTitle('Example');\n"
    "  });\n"
    "});\n"
)

VALID_CYPRESS = (
    "describe('Login', () => {\n"
    "  beforeEach(() => { cy.visit('/login'); });\n"
    "  it('logs in successfully', () => {\n"
    "    cy.get('#user').type('admin');\n"
    "    cy.get('button').click();\n"
    "    cy.contains('Dashboard').should('be.visible');\n"
    "  });\n"
    "});\n"
)

VALID_SELENIUM = (
    "import pytest\n"
    "from selenium import webdriver\n"
    "from selenium.webdriver.support.ui import WebDriverWait\n\n"
    "@pytest.fixture\n"
    "def driver():\n"
    "    d = webdriver.Chrome()\n"
    "    yield d\n"
    "    d.quit()\n\n"
    "def test_homepage_loads(driver):\n"
    "    driver.get('https://example.com')\n"
    "    assert 'Example' in driver.title\n"
)


# ---------------------------------------------------------------------------
# Playwright validation
# ---------------------------------------------------------------------------

class TestPlaywrightValidator:
    def test_should_pass_when_code_is_valid_playwright(self):
        result = validate_generated_code(VALID_PLAYWRIGHT, "playwright")
        assert result.passed is True
        assert result.reasons == []

    def test_should_fail_when_import_statement_is_missing(self):
        # Arrange: remove the import line
        code = VALID_PLAYWRIGHT.replace(
            "import { test, expect } from '@playwright/test';\n", ""
        )
        # Act
        result = validate_generated_code(code, "playwright")
        # Assert
        assert result.passed is False
        assert any("import" in r.lower() for r in result.reasons)

    def test_should_fail_when_no_test_calls_exist(self):
        # Arrange: replace test( with xtest( so it won't match
        code = "import { test, expect } from '@playwright/test';\nxtest('x', () => {});"
        result = validate_generated_code(code, "playwright")
        assert result.passed is False
        assert any("test(" in r for r in result.reasons)

    def test_should_fail_when_no_expect_assertion_present(self):
        code = (
            "import { test, expect } from '@playwright/test';\n"
            "test('no assertion', async () => { await page.goto('/'); });\n"
        )
        result = validate_generated_code(code, "playwright")
        assert result.passed is False
        assert any("expect" in r for r in result.reasons)

    def test_should_pass_with_spaced_import_variant(self):
        # Alternate style: import {test, expect}
        code = VALID_PLAYWRIGHT.replace(
            "import { test, expect }",
            "import {test, expect}"
        )
        result = validate_generated_code(code, "playwright")
        assert result.passed is True

    def test_should_be_case_insensitive_for_framework_name(self):
        result = validate_generated_code(VALID_PLAYWRIGHT, "PLAYWRIGHT")
        assert result.passed is True


# ---------------------------------------------------------------------------
# Cypress validation
# ---------------------------------------------------------------------------

class TestCypressValidator:
    def test_should_pass_when_code_is_valid_cypress(self):
        result = validate_generated_code(VALID_CYPRESS, "cypress")
        assert result.passed is True

    def test_should_fail_when_describe_block_missing(self):
        code = VALID_CYPRESS.replace("describe(", "xdescribe(")
        result = validate_generated_code(code, "cypress")
        assert result.passed is False
        assert any("describe" in r for r in result.reasons)

    def test_should_fail_when_it_block_missing(self):
        code = VALID_CYPRESS.replace("  it(", "  xit(")
        result = validate_generated_code(code, "cypress")
        assert result.passed is False
        assert any("it(" in r for r in result.reasons)

    def test_should_fail_when_cy_commands_missing(self):
        code = VALID_CYPRESS.replace("cy.", "XX.")
        result = validate_generated_code(code, "cypress")
        assert result.passed is False
        assert any("cy." in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Selenium validation
# ---------------------------------------------------------------------------

class TestSeleniumValidator:
    def test_should_pass_when_code_is_valid_selenium(self):
        result = validate_generated_code(VALID_SELENIUM, "selenium")
        assert result.passed is True

    def test_should_fail_when_import_pytest_missing(self):
        code = VALID_SELENIUM.replace("import pytest\n", "")
        result = validate_generated_code(code, "selenium")
        assert result.passed is False
        assert any("pytest" in r for r in result.reasons)

    def test_should_fail_when_webdriver_reference_missing(self):
        code = VALID_SELENIUM.replace("webdriver", "xwebdriver")
        result = validate_generated_code(code, "selenium")
        assert result.passed is False
        assert any("webdriver" in r.lower() for r in result.reasons)

    def test_should_fail_when_no_test_functions_defined(self):
        code = VALID_SELENIUM.replace("def test_", "def helper_")
        result = validate_generated_code(code, "selenium")
        assert result.passed is False
        assert any("def test_" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# validate_generated_code() edge cases
# ---------------------------------------------------------------------------

class TestValidateGeneratedCodeEdgeCases:
    def test_should_fail_when_code_is_empty_string(self):
        result = validate_generated_code("", "playwright")
        assert result.passed is False
        assert any("empty" in r.lower() for r in result.reasons)

    def test_should_fail_when_code_is_only_whitespace(self):
        result = validate_generated_code("   \n\t  ", "playwright")
        assert result.passed is False

    def test_should_pass_with_warning_for_unknown_framework(self):
        result = validate_generated_code("some arbitrary code", "jest")
        assert result.passed is True
        assert result.reasons  # warning reason present

    def test_should_bool_as_passed_attribute(self):
        result = validate_generated_code(VALID_PLAYWRIGHT, "playwright")
        assert bool(result) is True

    def test_should_repr_include_pass_or_fail(self):
        result = validate_generated_code(VALID_PLAYWRIGHT, "playwright")
        assert "PASS" in repr(result)


# ---------------------------------------------------------------------------
# sanitize_requirement() boundary/edge tests
# ---------------------------------------------------------------------------

class TestSanitizeRequirement:
    """These live here rather than a separate sanitizer test file so the
    generator test suite is self-contained for the critical generator cases."""

    def _sanitize(self, text, **kw):
        from common.sanitizer import sanitize_requirement
        return sanitize_requirement(text, **kw)

    def test_should_raise_sanitization_error_when_text_under_10_chars(self):
        from common.exceptions import SanitizationError
        with pytest.raises(SanitizationError, match="too short"):
            self._sanitize("short")

    def test_should_raise_sanitization_error_when_text_is_empty_string(self):
        from common.exceptions import SanitizationError
        with pytest.raises(SanitizationError):
            self._sanitize("")

    def test_should_raise_sanitization_error_when_text_exceeds_5000_chars(self):
        from common.exceptions import SanitizationError
        with pytest.raises(SanitizationError, match="exceeds"):
            self._sanitize("A" * 5001)

    def test_should_accept_exactly_10_char_boundary(self):
        result = self._sanitize("1234567890")
        assert result == "1234567890"

    def test_should_accept_exactly_5000_char_boundary(self):
        long_text = "A" * 5000
        result = self._sanitize(long_text)
        assert len(result) == 5000

    def test_should_strip_control_characters(self):
        # Arrange: embed a null byte and a BEL character
        text = "Test requirement\x00 with\x07 control chars"
        # Act
        result = self._sanitize(text)
        # Assert
        assert "\x00" not in result
        assert "\x07" not in result

    def test_should_strip_leading_trailing_whitespace(self):
        result = self._sanitize("  valid requirement  ")
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_should_raise_when_only_whitespace(self):
        from common.exceptions import SanitizationError
        with pytest.raises(SanitizationError):
            self._sanitize("         ")
