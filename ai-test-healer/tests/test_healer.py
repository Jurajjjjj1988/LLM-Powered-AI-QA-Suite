"""
Test strategy for ai-test-healer / healer.py
=============================================
Coverage targets:
  1. Cache key is (old_selector, sha256(html)): same selector + different HTML
     → cache miss → new Claude call.
  2. Cache hit increments applied_count by exactly 1.
  3. force_heal=True bypasses cache entirely.
  4. Claude returns "NONE" → persisted with validation_passed=False.
  5. Invalid CSS from Claude persists with validation_passed=False but is still
     returned without raising an exception.
  6. _extract_selector strips backtick and quote wrapping; takes first
     non-empty line when model returns multiple lines.
  7. ClaudeAPIError propagates out of heal().

All DB access uses SQLite :memory:. ClaudeClient is always mocked.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TOOL_ROOT = Path(__file__).parent.parent
REPO_ROOT = TOOL_ROOT.parent

for p in (str(TOOL_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from healer import SelfHealingEngine, _extract_selector
from common.schemas import HealSelectorRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_settings():
    from common.config import Settings
    settings = Settings.model_construct(
        anthropic_api_key="sk-ant-api03-" + "x" * 90,
        claude_model="claude-test-model",
        claude_max_tokens=128,
        claude_timeout_seconds=30,
        retry_max_attempts=1,
        retry_wait_min_seconds=0.0,
        retry_wait_max_seconds=0.0,
        db_path=Path(":memory:"),
        generator_default_framework="playwright",
        generator_output_dir=Path("./generated"),
        analyzer_flaky_threshold_percent=20.0,
        dashboard_host="127.0.0.1",
        dashboard_port=8000,
        log_level="DEBUG",
        log_json=False,
    )
    return settings


@pytest.fixture()
def engine(mem_settings, mocker):
    """Construct SelfHealingEngine with mocked Claude and in-memory DB."""
    import common.database as _db
    _db._engine = None
    _db._SessionLocal = None

    mock_claude = mocker.patch("healer.ClaudeClient", autospec=True)
    mock_claude.return_value.complete.return_value = ("button.submit", 20)

    with patch("healer.get_settings", return_value=mem_settings):
        inst = SelfHealingEngine(settings=mem_settings)
    inst._mock_claude = mock_claude
    return inst


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request(
    old_selector: str = "button#broken",
    html: str = "<html><body><button class='submit'>OK</button></body></html>",
    description: str = "Submit button",
    force_heal: bool = False,
) -> HealSelectorRequest:
    return HealSelectorRequest(
        old_selector=old_selector,
        html_snippet=html,
        description=description,
        force_heal=force_heal,
    )


# ---------------------------------------------------------------------------
# Cache key tests
# ---------------------------------------------------------------------------

class TestCacheKey:
    def test_should_cache_miss_when_html_differs_with_same_selector(
        self, engine, mem_settings
    ):
        """Same selector + different HTML → two Claude calls (no cache hit)."""
        # Arrange
        html_a = "<html><body><button class='submit'>OK</button></body></html>"
        html_b = "<html><body><input type='submit' value='Go'></body></html>"
        engine._client.complete.return_value = ("button.submit", 20)

        # Act
        engine.heal(_request(old_selector="button#broken", html=html_a))
        engine.heal(_request(old_selector="button#broken", html=html_b))

        # Assert: 2 Claude calls because HTML hashes differ
        assert engine._client.complete.call_count == 2

    def test_should_cache_hit_when_same_selector_and_html(
        self, engine, mem_settings
    ):
        """Same selector + same HTML → second call returns from_cache=True."""
        engine._client.complete.return_value = ("button.submit", 20)
        req = _request()

        first = engine.heal(req)
        second = engine.heal(req)

        assert first.from_cache is False
        assert second.from_cache is True

    def test_should_increment_applied_count_by_one_on_cache_hit(
        self, engine, mem_settings
    ):
        from common.database import get_session
        from common.models import HealedSelector

        engine._client.complete.return_value = ("button.submit", 20)
        req = _request()

        engine.heal(req)
        engine.heal(req)

        with get_session(mem_settings.db_path) as session:
            record = session.query(HealedSelector).first()
        # First use: applied_count = 1 (set on save)
        # Cache hit: applied_count incremented to 2
        assert record.applied_count == 2

    def test_should_bypass_cache_when_force_heal_true(self, engine, mem_settings):
        """force_heal=True must not read or write the cache, always calling Claude."""
        engine._client.complete.return_value = ("button.submit", 20)
        req = _request(force_heal=True)

        first = engine.heal(req)
        second = engine.heal(req)

        # Both should not be from_cache
        assert first.from_cache is False
        assert second.from_cache is False
        # Claude called twice
        assert engine._client.complete.call_count == 2


# ---------------------------------------------------------------------------
# NONE response handling
# ---------------------------------------------------------------------------

class TestNoneResponse:
    def test_should_persist_with_validation_passed_false_when_claude_returns_none(
        self, engine, mem_settings
    ):
        from common.database import get_session
        from common.models import HealedSelector

        engine._client.complete.return_value = ("NONE", 10)
        req = _request()

        response = engine.heal(req)

        assert response.new_selector == "NONE"
        assert response.validation_passed is False

        with get_session(mem_settings.db_path) as session:
            record = session.query(HealedSelector).first()
        assert record.new_selector == "NONE"
        assert record.validation_passed is False

    def test_should_persist_when_claude_returns_none_in_backticks(
        self, engine, mem_settings
    ):
        """Edge: model wraps NONE in backticks — _extract_selector strips them."""
        engine._client.complete.return_value = ("`NONE`", 10)
        response = engine.heal(_request())
        assert response.new_selector == "NONE"
        assert response.validation_passed is False


# ---------------------------------------------------------------------------
# Invalid CSS persistence
# ---------------------------------------------------------------------------

class TestInvalidCssPersistence:
    def test_should_persist_with_validation_passed_false_for_xpath_selector(
        self, engine, mem_settings
    ):
        from common.database import get_session
        from common.models import HealedSelector

        engine._client.complete.return_value = ("//div[@class='submit']", 15)
        response = engine.heal(_request())

        assert response.validation_passed is False
        # Must still return the selector (no exception)
        assert response.new_selector == "//div[@class='submit']"

        with get_session(mem_settings.db_path) as session:
            record = session.query(HealedSelector).first()
        assert record.validation_passed is False

    def test_should_not_raise_when_selector_is_invalid_css(
        self, engine
    ):
        """No exception must be raised even if the CSS is invalid."""
        engine._client.complete.return_value = ("???invalid###", 10)
        # Should not raise
        response = engine.heal(_request())
        assert response is not None
        assert response.validation_passed is False


# ---------------------------------------------------------------------------
# _extract_selector
# ---------------------------------------------------------------------------

class TestExtractSelector:
    def test_should_strip_backtick_wrapping(self):
        assert _extract_selector("`button.submit`") == "button.submit"

    def test_should_strip_double_quote_wrapping(self):
        assert _extract_selector('"button.submit"') == "button.submit"

    def test_should_strip_single_quote_wrapping(self):
        assert _extract_selector("'button.submit'") == "button.submit"

    def test_should_take_first_non_empty_line_when_multiple_lines(self):
        raw = "\n\nbutton.submit\n.other-line"
        result = _extract_selector(raw)
        assert result == "button.submit"

    def test_should_return_none_when_all_lines_empty(self):
        result = _extract_selector("   \n  \n  ")
        assert result == "NONE"

    def test_should_strip_surrounding_whitespace(self):
        assert _extract_selector("  button.submit  ") == "button.submit"

    def test_should_handle_bare_selector_with_no_wrapping(self):
        assert _extract_selector("div > span.highlight") == "div > span.highlight"


# ---------------------------------------------------------------------------
# ClaudeAPIError propagation
# ---------------------------------------------------------------------------

class TestClaudeAPIErrorPropagation:
    def test_should_propagate_claude_api_error_from_heal(self, engine):
        from common.exceptions import ClaudeAPIError

        engine._client.complete.side_effect = ClaudeAPIError("timeout")
        with pytest.raises(ClaudeAPIError):
            engine.heal(_request(force_heal=True))
