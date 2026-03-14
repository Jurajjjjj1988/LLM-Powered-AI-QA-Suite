"""
Test strategy for ai-test-generator / generate_tests.py
=========================================================
Focus areas:
  1. SHA-256 cache hit path:  second generate() call with same requirement+framework
     must return from_cache=True and insert zero new DB rows.
  2. _strip_code_fences():  removes ```typescript, bare ```, and preserves inner code.
  3. output_file path creation: parent dirs are created; file contents match
     the code returned by Claude mock.
  4. ClaudeAPIError propagation:  when the mock raises ClaudeAPIError the
     generator re-raises it without silently swallowing it.
  5. Cache is bypassed when use_cache=False.
  6. Validation failure still persists a DB row (validation_passed=False).

All DB access uses SQLite :memory: via a patched Settings object.
ClaudeClient is always mocked — no real API calls are ever made.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap – allow imports relative to ai-test-generator/
# ---------------------------------------------------------------------------
TOOL_ROOT = Path(__file__).parent.parent
REPO_ROOT = TOOL_ROOT.parent

for p in (str(TOOL_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_settings(tmp_path):
    """Return a Settings-like object pointing at an in-memory SQLite DB."""
    from common.config import Settings

    # Bypass pydantic-settings env loading; supply minimal required fields.
    settings = Settings.model_construct(
        anthropic_api_key="sk-ant-api03-" + "x" * 90,
        claude_model="claude-test-model",
        claude_max_tokens=2000,
        claude_timeout_seconds=30,
        retry_max_attempts=1,
        retry_wait_min_seconds=0.0,
        retry_wait_max_seconds=0.0,
        db_path=Path(":memory:"),
        generator_default_framework="playwright",
        generator_output_dir=tmp_path / "generated",
        analyzer_flaky_threshold_percent=20.0,
        dashboard_host="127.0.0.1",
        dashboard_port=8000,
        log_level="DEBUG",
        log_json=False,
    )
    return settings


@pytest.fixture()
def mock_claude(mocker):
    """Patch ClaudeClient.complete to return a known playwright snippet."""
    valid_code = (
        "import { test, expect } from '@playwright/test';\n"
        "test('loads homepage', async ({ page }) => {\n"
        "  await page.goto('https://example.com');\n"
        "  await expect(page).toHaveTitle('Example');\n"
        "});\n"
    )
    mock = mocker.patch(
        "generate_tests.ClaudeClient",
        autospec=True,
    )
    mock.return_value.complete.return_value = (valid_code, 120)
    return mock, valid_code


@pytest.fixture()
def generator(mem_settings, mock_claude):
    """Construct a TestGenerator with mocked Claude and in-memory DB."""
    from generate_tests import TestGenerator

    # Reset the module-level DB engine singleton so each test gets fresh state
    import common.database as _db
    _db._engine = None
    _db._SessionLocal = None

    with patch("generate_tests.get_settings", return_value=mem_settings):
        gen = TestGenerator(settings=mem_settings)
    return gen


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _playwright_request(requirement="Log in to the application with valid credentials", **kw):
    from common.schemas import GenerateTestsRequest
    return GenerateTestsRequest(requirement=requirement, framework="playwright", **kw)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStripCodeFences:
    """Unit tests for the module-level _strip_code_fences helper."""

    def _strip(self, text):
        from generate_tests import _strip_code_fences
        return _strip_code_fences(text)

    def test_should_remove_typescript_fence_when_present(self):
        # Arrange
        raw = "```typescript\nimport { test } from '@playwright/test';\n```"
        # Act
        result = self._strip(raw)
        # Assert
        assert "```" not in result
        assert "import { test }" in result

    def test_should_remove_bare_backtick_fence_when_present(self):
        # Arrange
        raw = "```\nsome code here\n```"
        # Act
        result = self._strip(raw)
        # Assert
        assert "```" not in result
        assert "some code here" in result

    def test_should_leave_code_unchanged_when_no_fences(self):
        # Arrange
        raw = "import { test } from '@playwright/test';"
        # Act
        result = self._strip(raw)
        # Assert
        assert result == raw

    def test_should_remove_python_fence_when_present(self):
        # Arrange
        raw = "```python\nimport pytest\n```"
        # Act
        result = self._strip(raw)
        # Assert
        assert "```python" not in result
        assert "import pytest" in result

    def test_should_handle_only_opening_fence_without_closing(self):
        # Arrange – model forgot to close the fence
        raw = "```typescript\nimport { test } from '@playwright/test';"
        # Act
        result = self._strip(raw)
        # Assert – opening fence stripped, trailing content kept
        assert "```typescript" not in result
        assert "import { test }" in result

    def test_should_return_empty_string_when_input_is_empty(self):
        assert self._strip("") == ""


class TestCacheHit:
    """Verify that a second identical request returns from_cache=True."""

    def test_should_return_from_cache_true_when_same_requirement_called_twice(
        self, generator
    ):
        # Arrange
        req = _playwright_request(use_cache=True)

        # Act
        first = generator.generate(req)
        second = generator.generate(req)

        # Assert
        assert first.from_cache is False
        assert second.from_cache is True
        assert second.generated_code == first.generated_code

    def test_should_insert_zero_new_db_rows_on_cache_hit(self, generator, mem_settings):
        # Arrange
        from common.database import get_session
        from common.models import GeneratedTest

        req = _playwright_request(use_cache=True)

        # Act
        generator.generate(req)
        generator.generate(req)

        # Assert: only 1 row in DB even after 2 calls
        with get_session(mem_settings.db_path) as session:
            count = session.query(GeneratedTest).count()
        assert count == 1

    def test_should_bypass_cache_when_use_cache_false(self, generator, mem_settings):
        # Arrange
        from common.database import get_session
        from common.models import GeneratedTest

        req_cached = _playwright_request(use_cache=False)

        # Act
        generator.generate(req_cached)
        generator.generate(req_cached)

        # Assert: two DB rows because cache was not used
        with get_session(mem_settings.db_path) as session:
            count = session.query(GeneratedTest).count()
        assert count == 2


class TestOutputFileCreation:
    """Verify that output_file triggers parent directory creation and correct content."""

    def test_should_create_parent_dirs_and_write_correct_content(
        self, generator, tmp_path, mock_claude
    ):
        # Arrange
        _, expected_code = mock_claude
        output_path = tmp_path / "nested" / "deep" / "test_output.ts"
        req = _playwright_request(output_file=output_path)

        # Act
        response = generator.generate(req)

        # Assert
        assert output_path.exists(), "Output file was not created"
        written = output_path.read_text(encoding="utf-8")
        assert written == expected_code
        assert response.output_file_path is not None

    def test_should_still_succeed_when_output_file_is_none(self, generator):
        # Arrange
        req = _playwright_request(output_file=None)
        # Act
        response = generator.generate(req)
        # Assert
        assert response.output_file_path is None
        assert response.generated_code


class TestClaudeAPIErrorPropagation:
    """Ensure ClaudeAPIError from the client bubbles out of generate()."""

    def test_should_propagate_claude_api_error_when_client_raises(
        self, generator, mocker
    ):
        from common.exceptions import ClaudeAPIError

        # Arrange
        generator._client.complete.side_effect = ClaudeAPIError("timeout")
        req = _playwright_request(use_cache=False)

        # Act / Assert
        with pytest.raises(ClaudeAPIError):
            generator.generate(req)


class TestValidationFailurePersistence:
    """Even if validation fails, the record must be persisted with validation_passed=False."""

    def test_should_persist_record_with_validation_passed_false_on_bad_code(
        self, generator, mocker, mem_settings
    ):
        from common.database import get_session
        from common.models import GeneratedTest

        # Arrange: return invalid code (no import, no test calls)
        generator._client.complete.return_value = ("console.log('hello');", 10)
        req = _playwright_request(use_cache=False)

        # Act
        response = generator.generate(req)

        # Assert
        assert response.validation_passed is False
        with get_session(mem_settings.db_path) as session:
            row = session.query(GeneratedTest).first()
        assert row is not None
        assert row.validation_passed is False


class TestSystemPromptSafety:
    """User-supplied requirement text MUST NOT appear in SYSTEM_PROMPT."""

    def test_should_not_contain_user_content_in_system_prompt(self):
        from prompts import SYSTEM_PROMPT

        # Sample user-supplied text that might be injected
        user_texts = [
            "Log in to the application with valid credentials",
            "Add items to cart and complete checkout",
            "Reset password via email link",
        ]
        for text in user_texts:
            assert text not in SYSTEM_PROMPT, (
                f"User requirement text found in SYSTEM_PROMPT: {text!r}"
            )
