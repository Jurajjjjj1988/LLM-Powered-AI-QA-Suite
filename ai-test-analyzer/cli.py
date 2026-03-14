"""
Click CLI entry-point for ai-test-analyzer.

Usage examples:
  python cli.py analyze results.json
  python cli.py analyze results.xml --source-label "nightly CI"
  python cli.py analyze results.json --threshold 15.0
  # pipe raw JSON entries directly
  echo '[{"test":"login","status":"FAIL","duration":2.1}]' | python cli.py analyze -
"""
from __future__ import annotations

import json
import logging
import sys

import click

from common.config import get_settings
from common.exceptions import ClaudeAPIError
from common.logging_config import configure_logging
from common.schemas import FlakyAnalysisRequest, TestLogEntry

from analyze_flaky import FlakyAnalyzer
from log_parser import parse_log_file, parse_log_entries

logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """AI Test Analyzer — detect and explain flaky tests using Claude."""


@cli.command("analyze")
@click.argument("log_source", metavar="LOG_FILE_OR_DASH")
@click.option(
    "--source-label",
    default=None,
    help="Human-readable label stored as source_file in the DB.",
)
@click.option(
    "--threshold",
    type=float,
    default=None,
    help="Override the flaky threshold percentage (default from settings).",
)
@click.option(
    "--no-ai",
    is_flag=True,
    default=False,
    help="Skip Claude call; only compute and persist stats.",
)
def analyze_cmd(
    log_source: str,
    source_label: str | None,
    threshold: float | None,
    no_ai: bool,
) -> None:
    """
    Analyze LOG_FILE_OR_DASH for flaky tests.

    Pass '-' to read JSON from stdin.
    Supported formats: JSON array, JUnit XML, plain-text CI logs.
    """
    settings = get_settings()

    # Allow threshold override before initialising analyzer
    if threshold is not None:
        settings.analyzer_flaky_threshold_percent = threshold  # type: ignore[misc]

    configure_logging(settings, tool_name="ai-test-analyzer")

    # --- Load entries -------------------------------------------------------
    try:
        if log_source == "-":
            raw = sys.stdin.read()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                click.echo(f"stdin is not valid JSON: {exc}", err=True)
                sys.exit(1)
            if isinstance(data, dict):
                for key in ("results", "tests", "entries"):
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
            entries = parse_log_entries(data)
            source = source_label or "stdin"
        else:
            entries = parse_log_file(log_source)
            source = source_label or log_source
    except (FileNotFoundError, ValueError) as exc:
        click.echo(f"Failed to load log source: {exc}", err=True)
        sys.exit(1)

    if not entries:
        click.echo("No test entries found in the provided source.", err=True)
        sys.exit(1)

    click.echo(f"Loaded {len(entries)} test entries from '{source}'")

    # --- Analyse ------------------------------------------------------------
    request = FlakyAnalysisRequest(logs=entries, source_file=source)

    try:
        analyzer = FlakyAnalyzer(settings)
        response = analyzer.analyze(request)
    except ClaudeAPIError as exc:
        click.echo(f"Claude API error: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:
        logger.exception("Unexpected error during analysis")
        click.echo(f"Unexpected error: {exc}", err=True)
        sys.exit(3)

    # --- Report -------------------------------------------------------------
    click.echo(
        f"\nAnalysis complete  [run_id={response.run_id}  "
        f"total={response.total_analyzed}  flaky={len(response.flaky_tests)}]"
    )

    if not response.flaky_tests:
        click.echo("No flaky tests detected above the threshold.")
        return

    click.echo("\n" + "─" * 72)
    for detail in response.flaky_tests:
        click.echo(
            f"  {detail.test_name}\n"
            f"    fail_rate={detail.fail_rate:.1f}%  "
            f"runs={detail.total_runs}  "
            f"avg_duration={detail.avg_duration_seconds:.2f}s"
        )
        if detail.ai_suggestion:
            for line in detail.ai_suggestion.splitlines():
                click.echo(f"    {line}")
        click.echo()
    click.echo("─" * 72)


if __name__ == "__main__":
    cli()
