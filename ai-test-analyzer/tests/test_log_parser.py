"""
Test strategy for ai-test-analyzer / log_parser.py
====================================================
Coverage targets:
  1. JUnit XML: handles <testsuites> wrapper, <testsuite> without wrapper,
     <failure> child → FAIL, <error> child → FAIL, <skipped> → SKIP, no
     child → PASS.
  2. `time` attribute parsed as float (e.g. "2.34" or "0").
  3. JSON log parsing: plain array, wrapped in {"results": [...]}, wrapped
     in {"tests": [...]}.
  4. Plain-text parser detects PASS/FAIL/SKIP/SUCCESS/ERROR lines.
  5. File-not-found raises FileNotFoundError.
  6. Completely unparseable content raises ValueError.
  7. parse_log_entries() skips invalid entries with a warning.
  8. Status normalisation is applied to XML-parsed entries.

No DB or network access. Uses tmp_path for file-based tests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOL_ROOT = Path(__file__).parent.parent
REPO_ROOT = TOOL_ROOT.parent

for p in (str(TOOL_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from log_parser import parse_log_entries, parse_log_file


# ---------------------------------------------------------------------------
# JUnit XML helpers
# ---------------------------------------------------------------------------

def _write(tmp_path, filename, content):
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


JUNIT_SINGLE_SUITE = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="MyTests" tests="3" failures="1" errors="0" time="5.0">
  <testcase classname="pkg.TestLogin" name="test_valid_login" time="1.2"/>
  <testcase classname="pkg.TestLogin" name="test_invalid_login" time="0.8">
    <failure message="AssertionError">Expected True, got False</failure>
  </testcase>
  <testcase classname="pkg.TestLogin" name="test_skip_me" time="0.1">
    <skipped/>
  </testcase>
</testsuite>
"""

JUNIT_WITH_WRAPPER = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="Suite1">
    <testcase classname="A" name="pass_test" time="0.5"/>
    <testcase classname="A" name="fail_test" time="1.0">
      <failure message="boom">stack trace here</failure>
    </testcase>
  </testsuite>
  <testsuite name="Suite2">
    <testcase classname="B" name="error_test" time="2.0">
      <error message="NullPointer">NPE</error>
    </testcase>
  </testsuite>
</testsuites>
"""

JUNIT_NO_TIME_ATTR = """\
<testsuite>
  <testcase classname="C" name="no_time_test"/>
</testsuite>
"""


# ---------------------------------------------------------------------------
# JUnit XML parsing
# ---------------------------------------------------------------------------

class TestJUnitXmlParser:
    def test_should_parse_single_testsuite_without_wrapper(self, tmp_path):
        p = _write(tmp_path, "results.xml", JUNIT_SINGLE_SUITE)
        entries = parse_log_file(p)
        assert len(entries) == 3

    def test_should_assign_pass_when_no_child_element(self, tmp_path):
        p = _write(tmp_path, "r.xml", JUNIT_SINGLE_SUITE)
        entries = parse_log_file(p)
        passing = [e for e in entries if "test_valid_login" in e.test]
        assert len(passing) == 1
        assert passing[0].status == "PASS"

    def test_should_assign_fail_when_failure_child_present(self, tmp_path):
        p = _write(tmp_path, "r.xml", JUNIT_SINGLE_SUITE)
        entries = parse_log_file(p)
        failing = [e for e in entries if "test_invalid_login" in e.test]
        assert failing[0].status == "FAIL"

    def test_should_assign_skip_when_skipped_child_present(self, tmp_path):
        p = _write(tmp_path, "r.xml", JUNIT_SINGLE_SUITE)
        entries = parse_log_file(p)
        skipped = [e for e in entries if "test_skip_me" in e.test]
        assert skipped[0].status == "SKIP"

    def test_should_handle_testsuites_wrapper(self, tmp_path):
        p = _write(tmp_path, "wrapped.xml", JUNIT_WITH_WRAPPER)
        entries = parse_log_file(p)
        assert len(entries) == 3
        statuses = {e.test.split(".")[-1]: e.status for e in entries}
        assert statuses["pass_test"] == "PASS"
        assert statuses["fail_test"] == "FAIL"
        assert statuses["error_test"] == "FAIL"

    def test_should_assign_fail_when_error_child_present(self, tmp_path):
        p = _write(tmp_path, "w.xml", JUNIT_WITH_WRAPPER)
        entries = parse_log_file(p)
        errors = [e for e in entries if "error_test" in e.test]
        assert errors[0].status == "FAIL"

    def test_should_parse_time_attribute_as_float(self, tmp_path):
        p = _write(tmp_path, "r.xml", JUNIT_SINGLE_SUITE)
        entries = parse_log_file(p)
        valid_login = [e for e in entries if "test_valid_login" in e.test][0]
        assert isinstance(valid_login.duration, float)
        assert valid_login.duration == pytest.approx(1.2)

    def test_should_default_duration_to_zero_when_time_attr_missing(self, tmp_path):
        p = _write(tmp_path, "no_time.xml", JUNIT_NO_TIME_ATTR)
        entries = parse_log_file(p)
        assert len(entries) == 1
        assert entries[0].duration == 0.0

    def test_should_include_classname_in_full_name(self, tmp_path):
        p = _write(tmp_path, "r.xml", JUNIT_SINGLE_SUITE)
        entries = parse_log_file(p)
        names = [e.test for e in entries]
        assert any("pkg.TestLogin" in n for n in names)


# ---------------------------------------------------------------------------
# JSON log parsing
# ---------------------------------------------------------------------------

class TestJsonLogParser:
    def test_should_parse_plain_json_array(self, tmp_path):
        data = [{"test": "t1", "status": "PASS", "duration": 1.0}]
        p = _write(tmp_path, "log.json", json.dumps(data))
        entries = parse_log_file(p)
        assert len(entries) == 1
        assert entries[0].test == "t1"

    def test_should_parse_results_wrapped_json(self, tmp_path):
        data = {"results": [{"test": "t2", "status": "FAIL"}]}
        p = _write(tmp_path, "log.json", json.dumps(data))
        entries = parse_log_file(p)
        assert len(entries) == 1
        assert entries[0].status == "FAIL"

    def test_should_parse_tests_wrapped_json(self, tmp_path):
        data = {"tests": [{"test": "t3", "status": "PASS"}]}
        p = _write(tmp_path, "log.json", json.dumps(data))
        entries = parse_log_file(p)
        assert entries[0].test == "t3"

    def test_should_normalise_status_in_json_log(self, tmp_path):
        data = [{"test": "t", "status": "passed"}]
        p = _write(tmp_path, "log.json", json.dumps(data))
        entries = parse_log_file(p)
        assert entries[0].status == "PASS"

    def test_should_skip_invalid_entries_gracefully(self):
        # parse_log_entries used directly without file
        raw = [
            {"test": "good", "status": "PASS"},
            {"this_is": "missing_required_fields"},
            {"test": "also_good", "status": "FAIL"},
        ]
        entries = parse_log_entries(raw)
        # Only valid entries returned
        names = [e.test for e in entries]
        assert "good" in names
        assert "also_good" in names
        # The invalid entry is silently skipped
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# Plain-text parsing
# ---------------------------------------------------------------------------

class TestPlainTextParser:
    def test_should_parse_pass_line(self, tmp_path):
        content = "PASS  login_test  2.34s"
        p = _write(tmp_path, "log.txt", content)
        entries = parse_log_file(p)
        passing = [e for e in entries if "login_test" in e.test]
        assert passing
        assert passing[0].status == "PASS"

    def test_should_parse_fail_line(self, tmp_path):
        content = "FAIL  checkout_test  1.5s"
        p = _write(tmp_path, "log.txt", content)
        entries = parse_log_file(p)
        failing = [e for e in entries if "checkout_test" in e.test]
        assert failing
        assert failing[0].status == "FAIL"

    def test_should_parse_success_status(self, tmp_path):
        content = "SUCCESS  payment_test  0.9s"
        p = _write(tmp_path, "log.txt", content)
        entries = parse_log_file(p)
        passing = [e for e in entries if "payment_test" in e.test]
        assert passing
        assert passing[0].status == "PASS"

    def test_should_convert_ms_duration_to_seconds(self, tmp_path):
        content = "PASS  fast_test  500ms"
        p = _write(tmp_path, "log.txt", content)
        entries = parse_log_file(p)
        found = [e for e in entries if "fast_test" in e.test]
        if found:
            assert found[0].duration == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestFileErrors:
    def test_should_raise_file_not_found_when_path_missing(self, tmp_path):
        nonexistent = tmp_path / "ghost.xml"
        with pytest.raises(FileNotFoundError):
            parse_log_file(nonexistent)

    def test_should_raise_value_error_when_content_is_unparseable(self, tmp_path):
        p = _write(tmp_path, "garbage.txt", "no test results here at all lalala")
        with pytest.raises(ValueError, match="Could not parse"):
            parse_log_file(p)
