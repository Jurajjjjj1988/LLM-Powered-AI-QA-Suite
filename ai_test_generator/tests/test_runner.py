"""Tests for the shared closed-loop execution runner (common.test_runner)."""

from __future__ import annotations

from pathlib import Path

from common.test_runner import parse_playwright_verdict, run_playwright_test


class TestParseVerdict:
    def test_should_be_green_on_exit0_with_a_real_passing_tally(self):
        result = parse_playwright_verdict("  1 passed (2.1s)", exit_code=0)
        assert result.passed is True
        assert result.passed_count == 1
        assert result.failed_count == 0

    def test_should_not_be_green_when_a_test_failed(self):
        result = parse_playwright_verdict("  1 passed\n  2 failed", exit_code=1)
        assert result.passed is False
        assert result.failed_count == 2

    def test_should_not_be_green_on_a_flaky_pass(self):
        result = parse_playwright_verdict("  3 passed\n  1 flaky", exit_code=0)
        assert result.passed is False

    def test_should_not_be_green_when_nothing_passed_all_skipped(self):
        # A "passed" substring must not fake green — zero passed count.
        result = parse_playwright_verdict("  0 passed\n  4 skipped", exit_code=0)
        assert result.passed is False
        assert result.passed_count == 0

    def test_should_not_be_green_when_exit_nonzero_despite_a_passed_line(self):
        result = parse_playwright_verdict("  1 passed", exit_code=1)
        assert result.passed is False

    def test_should_count_timed_out_and_interrupted_as_not_green(self):
        result = parse_playwright_verdict("  1 passed\n  1 timed out", exit_code=1)
        assert result.passed is False
        assert result.failed_count == 1


class TestRunPlaywright:
    def test_should_run_the_spec_and_return_the_parsed_verdict(self, mocker):
        completed = mocker.Mock(stdout="  1 passed (1s)", stderr="", returncode=0)
        run = mocker.patch("common.test_runner.subprocess.run", return_value=completed)

        result = run_playwright_test(Path("foo.spec.ts"), "https://example.com")

        assert result.passed is True
        # invoked playwright against the spec, with BASE_URL exported
        args, kwargs = run.call_args
        assert args[0][:3] == ["npx", "playwright", "test"]
        assert kwargs["env"]["BASE_URL"] == "https://example.com"

    def test_should_surface_a_red_run_as_a_result_not_an_exception(self, mocker):
        completed = mocker.Mock(stdout="  0 passed\n  1 failed", stderr="", returncode=1)
        mocker.patch("common.test_runner.subprocess.run", return_value=completed)

        result = run_playwright_test(Path("foo.spec.ts"), "https://example.com")

        assert result.passed is False
        assert result.failed_count == 1
