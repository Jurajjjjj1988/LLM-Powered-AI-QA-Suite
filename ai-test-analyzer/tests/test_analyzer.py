"""
Test strategy for ai-test-analyzer / analyze_flaky.py
=======================================================
Coverage targets:
  1. Status normalisation: passed/PASSED/SUCCESS/ok → PASS;
     failed/FAILURE/ERROR → FAIL; SKIP excluded from denominator.
  2. SKIP entries excluded from total_runs in fail_rate calculation.
  3. Batch boundary: 10 tests → 1 Claude call; 11 tests → 2 calls.
  4. _parse_suggestions_json: valid JSON, JSON in ```json fences, garbage → no exception.
  5. FlakyTestRun + FlakyTestResult persist in one transaction.
  6. Rollback on DB error leaves no orphan rows.

All DB access uses SQLite :memory:. ClaudeClient is always mocked.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TOOL_ROOT = Path(__file__).parent.parent
REPO_ROOT = TOOL_ROOT.parent

for p in (str(TOOL_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from analyze_flaky import FlakyAnalyzer, _aggregate_stats, _parse_suggestions_json
from common.schemas import FlakyAnalysisRequest, TestLogEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_settings():
    from common.config import Settings
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
        generator_output_dir=Path("./generated"),
        analyzer_flaky_threshold_percent=20.0,
        dashboard_host="127.0.0.1",
        dashboard_port=8000,
        log_level="DEBUG",
        log_json=False,
    )
    return settings


def _make_ai_response(test_names: list[str]) -> str:
    """Build a valid Claude JSON response for given test names."""
    return json.dumps([
        {"test_name": n, "root_cause": "timing", "fixes": ["add wait"]}
        for n in test_names
    ])


@pytest.fixture()
def analyzer(mem_settings, mocker):
    """Construct a FlakyAnalyzer with mocked Claude and in-memory DB."""
    import common.database as _db
    _db._engine = None
    _db._SessionLocal = None

    mock_client = mocker.patch("analyze_flaky.ClaudeClient", autospec=True)
    mock_client.return_value.complete.return_value = (_make_ai_response([]), 50)

    with patch("analyze_flaky.get_settings", return_value=mem_settings):
        inst = FlakyAnalyzer(settings=mem_settings)
    # Expose mock for tests that need to configure it
    inst._mock_client_class = mock_client
    return inst


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(test: str, status: str, duration: float = 1.0) -> TestLogEntry:
    return TestLogEntry(test=test, status=status, duration=duration)


def _make_logs_for_n_tests(n: int, fail_rate: float = 1.0) -> list[TestLogEntry]:
    """
    Generate log entries for *n* distinct test names, each with one FAIL and
    one PASS so fail_rate=50% which exceeds the 20% threshold.
    """
    logs = []
    for i in range(n):
        name = f"test_{i:03d}"
        logs.append(_entry(name, "FAIL"))
        logs.append(_entry(name, "PASS"))
    return logs


# ---------------------------------------------------------------------------
# Status normalisation (via TestLogEntry.normalize_status validator)
# ---------------------------------------------------------------------------

class TestStatusNormalisation:
    @pytest.mark.parametrize("raw,expected", [
        ("passed",  "PASS"),
        ("PASSED",  "PASS"),
        ("SUCCESS", "PASS"),
        ("ok",      "PASS"),
        ("OK",      "PASS"),
        ("failed",  "FAIL"),
        ("FAILED",  "FAIL"),
        ("FAILURE", "FAIL"),
        ("ERROR",   "FAIL"),
        ("SKIP",    "SKIP"),
        ("SKIPPED", "SKIP"),
        ("IGNORED", "SKIP"),
        ("PASS",    "PASS"),
        ("FAIL",    "FAIL"),
    ])
    def test_should_normalize_status_correctly(self, raw, expected):
        entry = TestLogEntry(test="t", status=raw)
        assert entry.status == expected


# ---------------------------------------------------------------------------
# SKIP exclusion from denominator
# ---------------------------------------------------------------------------

class TestSkipExclusion:
    def test_should_exclude_skip_from_total_runs_denominator(self):
        # Arrange: 2 PASS + 2 FAIL + 6 SKIP = 10 entries, but denominator = 4
        entries = (
            [_entry("flaky", "PASS")] * 2
            + [_entry("flaky", "FAIL")] * 2
            + [_entry("flaky", "SKIP")] * 6
        )
        # Act
        stats = _aggregate_stats(entries)
        # Assert: fail_rate = 2 / (2+2) * 100 = 50.0, total_runs = 4
        assert stats["flaky"]["total_runs"] == 4
        assert stats["flaky"]["fail_rate"] == pytest.approx(50.0)

    def test_should_have_zero_fail_rate_when_all_entries_are_skip(self):
        entries = [_entry("t", "SKIP")] * 5
        stats = _aggregate_stats(entries)
        assert stats["t"]["total_runs"] == 0
        assert stats["t"]["fail_rate"] == 0.0


# ---------------------------------------------------------------------------
# Batch boundary: Claude call count
# ---------------------------------------------------------------------------

class TestBatchBoundary:
    def test_should_make_one_claude_call_for_10_flaky_tests(
        self, analyzer, mem_settings, mocker
    ):
        # Arrange: 10 distinct tests all with 100% fail rate (exceeds threshold)
        logs = _make_logs_for_n_tests(10)
        response_json = _make_ai_response([f"test_{i:03d}" for i in range(10)])
        analyzer._client.complete.return_value = (response_json, 100)

        request = FlakyAnalysisRequest(logs=logs, source_file=None)
        # Act
        analyzer.analyze(request)
        # Assert: exactly 1 call
        assert analyzer._client.complete.call_count == 1

    def test_should_make_two_claude_calls_for_11_flaky_tests(
        self, analyzer, mem_settings
    ):
        # Arrange: 11 distinct tests, all flaky
        logs = _make_logs_for_n_tests(11)
        response_json_10 = _make_ai_response([f"test_{i:03d}" for i in range(10)])
        response_json_1  = _make_ai_response(["test_010"])
        analyzer._client.complete.side_effect = [
            (response_json_10, 100),
            (response_json_1,  20),
        ]

        request = FlakyAnalysisRequest(logs=logs, source_file=None)
        # Act
        analyzer.analyze(request)
        # Assert: exactly 2 calls
        assert analyzer._client.complete.call_count == 2


# ---------------------------------------------------------------------------
# _parse_suggestions_json
# ---------------------------------------------------------------------------

class TestParseSuggestionsJson:
    def test_should_parse_valid_json_array(self):
        raw = json.dumps([{"test_name": "t1", "root_cause": "timing", "fixes": []}])
        result = _parse_suggestions_json(raw, expected_count=1)
        assert len(result) == 1
        assert result[0]["test_name"] == "t1"

    def test_should_parse_json_wrapped_in_json_fences(self):
        inner = json.dumps([{"test_name": "t1", "root_cause": "x", "fixes": []}])
        raw = f"```json\n{inner}\n```"
        result = _parse_suggestions_json(raw, expected_count=1)
        assert len(result) == 1

    def test_should_parse_json_wrapped_in_bare_fences(self):
        inner = json.dumps([{"test_name": "t1", "root_cause": "x", "fixes": []}])
        raw = f"```\n{inner}\n```"
        result = _parse_suggestions_json(raw, expected_count=1)
        assert len(result) == 1

    def test_should_return_empty_list_on_garbage_input(self):
        result = _parse_suggestions_json("this is not json at all!!!", expected_count=2)
        assert result == []

    def test_should_return_empty_list_when_input_is_empty_string(self):
        result = _parse_suggestions_json("", expected_count=1)
        assert result == []

    def test_should_pad_result_to_expected_count_when_short(self):
        raw = json.dumps([{"test_name": "t1", "root_cause": "x", "fixes": []}])
        result = _parse_suggestions_json(raw, expected_count=3)
        assert len(result) == 3
        assert result[1] == {}  # padded empty dict
        assert result[2] == {}

    def test_should_truncate_result_to_expected_count_when_long(self):
        raw = json.dumps([{"test_name": f"t{i}"} for i in range(5)])
        result = _parse_suggestions_json(raw, expected_count=2)
        assert len(result) == 2

    def test_should_return_empty_list_when_json_is_object_not_array(self):
        raw = json.dumps({"test_name": "t1"})
        result = _parse_suggestions_json(raw, expected_count=1)
        assert result == []

    def test_should_extract_array_embedded_in_prose(self):
        inner = json.dumps([{"test_name": "t1", "root_cause": "x", "fixes": []}])
        raw = f"Here is my analysis:\n{inner}\nThat's all."
        result = _parse_suggestions_json(raw, expected_count=1)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# DB persistence — FlakyTestRun + FlakyTestResult in one transaction
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_should_persist_flaky_run_and_results_together(
        self, analyzer, mem_settings
    ):
        from common.database import get_session
        from common.models import FlakyTestResult, FlakyTestRun

        # Arrange: 1 flaky test
        logs = [_entry("flaky_test", "FAIL"), _entry("flaky_test", "PASS")]
        response_json = _make_ai_response(["flaky_test"])
        analyzer._client.complete.return_value = (response_json, 50)
        request = FlakyAnalysisRequest(logs=logs, source_file="ci.log")

        # Act
        response = analyzer.analyze(request)

        # Assert
        with get_session(mem_settings.db_path) as session:
            run = session.query(FlakyTestRun).filter_by(id=response.run_id).first()
            assert run is not None
            assert run.source_file == "ci.log"
            assert run.flaky_count == 1

            results = session.query(FlakyTestResult).filter_by(run_id=run.id).all()
            assert len(results) == 1
            assert results[0].test_name == "flaky_test"

    def test_should_leave_no_orphan_rows_on_db_error(
        self, analyzer, mem_settings, mocker
    ):
        from common.database import get_session
        from common.models import FlakyTestRun

        # Arrange: make get_session raise to simulate DB error
        logs = [_entry("t", "FAIL"), _entry("t", "PASS")]
        analyzer._client.complete.return_value = (_make_ai_response(["t"]), 50)

        original_save = None
        import repository as repo_mod
        with mocker.patch.object(
            repo_mod,
            "save_flaky_run",
            side_effect=Exception("disk full"),
        ):
            with pytest.raises(Exception):
                analyzer.analyze(FlakyAnalysisRequest(logs=logs))

        # Assert: no FlakyTestRun rows were committed
        with get_session(mem_settings.db_path) as session:
            count = session.query(FlakyTestRun).count()
        assert count == 0
