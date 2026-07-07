"""
Click CLI entry-point for ai-test-generator.

Usage examples:
  python cli.py generate "User can log in with valid credentials" --framework playwright
  python cli.py generate "..." --framework cypress --output-file ./out/login.spec.ts
  python cli.py generate "..." --no-cache
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from ai_test_generator.generate_tests import TestGenerator, VerifiedGeneration
from ai_test_generator.jira_ticket import parse_ticket
from common.config import get_settings
from common.exceptions import ClaudeAPIError, SanitizationError, TicketParseError
from common.logging_config import configure_logging
from common.schemas import (
    GenerateFromTicketRequest,
    GenerateTestsRequest,
    GenerateTestsResponse,
)

logger = logging.getLogger(__name__)


def _report_run(
    response: GenerateTestsResponse,
    verified: VerifiedGeneration | None,
    *,
    quality_label: str,
) -> None:
    """Echo the generation summary: source, quality gate, output file, closed-loop verdict."""
    source = "cache" if response.from_cache else "Claude API"
    quality = "PASSED" if response.validation_passed else "FAILED"
    click.echo(
        f"\nGeneration complete  [source={source}  {quality_label}={quality}  "
        f"tokens={response.tokens_used}  id={response.id}]"
    )
    if response.output_file_path:
        click.echo(f"Written to: {response.output_file_path}")
    if verified is not None and verified.execution_passed is not None:
        verdict = "GREEN" if verified.execution_passed else "RED"
        click.echo(f"Closed loop: execution={verdict}  repairs={verified.repair_attempts}")


@click.group()
def cli() -> None:
    """AI Test Generator — generate Playwright/Cypress/Selenium tests from requirements."""


@cli.command("generate")
@click.argument("requirement")
@click.option(
    "--framework",
    type=click.Choice(["playwright", "cypress", "selenium"], case_sensitive=False),
    default="playwright",
    show_default=True,
    help="Test framework to target.",
)
@click.option(
    "--output-file",
    type=click.Path(dir_okay=False, writable=True),
    default=None,
    help="Write generated code to this file path.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Skip cache lookup and always call Claude.",
)
@click.option(
    "--show-code/--no-show-code",
    default=True,
    help="Print generated code to stdout.",
)
@click.option(
    "--url",
    default=None,
    help="Closed loop: run the generated Playwright test against this base URL and "
    "repair until it passes. Requires --output-file + Node/Playwright installed.",
)
def generate_cmd(
    requirement: str,
    framework: str,
    output_file: str | None,
    no_cache: bool,
    show_code: bool,
    url: str | None,
) -> None:
    """Generate tests for REQUIREMENT (a plain-text description of the feature)."""
    settings = get_settings()
    configure_logging(settings, tool_name="ai-test-generator")

    request = GenerateTestsRequest(
        requirement=requirement,
        framework=framework,
        output_file=output_file,  # type: ignore[arg-type]
        use_cache=not no_cache,
    )

    verified = None
    try:
        generator = TestGenerator(settings)
        if url:
            verified = generator.generate_and_verify(request, base_url=url)
            response = verified.response
        else:
            response = generator.generate(request)
    except SanitizationError as exc:
        click.echo(f"Input error: {exc}", err=True)
        sys.exit(1)
    except ClaudeAPIError as exc:
        click.echo(f"Claude API error: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:
        logger.exception("Unexpected error during generation")
        click.echo(f"Unexpected error: {exc}", err=True)
        sys.exit(3)

    _report_run(response, verified, quality_label="validation")

    if not response.validation_passed:
        click.echo(
            "WARNING: validation failed — the generated code may not be runnable.",
            err=True,
        )

    if show_code:
        click.echo("\n" + "─" * 72)
        click.echo(response.generated_code)
        click.echo("─" * 72)


@cli.command("from-jira")
@click.argument("ticket_file", type=click.Path(dir_okay=False), required=False)
@click.option(
    "--stdin",
    is_flag=True,
    default=False,
    help="Read the ticket from STDIN instead of a file (also works with '-').",
)
@click.option(
    "--framework",
    type=click.Choice(["playwright", "cypress", "selenium"], case_sensitive=False),
    default="playwright",
    show_default=True,
    help="Test framework to target.",
)
@click.option(
    "--output-file",
    type=click.Path(dir_okay=False, writable=True),
    default=None,
    help="Write generated code to this file path.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Skip cache lookup and always call Claude.",
)
@click.option("--show-code/--no-show-code", default=True, help="Print generated code to stdout.")
@click.option(
    "--url",
    default=None,
    help="Closed loop: run the generated test against this base URL and repair until green.",
)
def from_jira_cmd(
    ticket_file: str | None,
    stdin: bool,
    framework: str,
    output_file: str | None,
    no_cache: bool,
    show_code: bool,
    url: str | None,
) -> None:
    """Generate tests FROM a ticket — one traceable test per acceptance criterion.

    TICKET_FILE is a markdown/plain-text work item (a Jira export, or the output of
    `gh issue view`). Use '-' or --stdin to read from STDIN. Example:

      gh issue view 42 --repo owner/repo > TICKET.md

      ai-test-generator from-jira TICKET.md --output-file suite.spec.ts --url https://app
    """
    settings = get_settings()
    configure_logging(settings, tool_name="ai-test-generator")

    if stdin or ticket_file in (None, "-"):
        raw = sys.stdin.read()
    else:
        raw = Path(ticket_file).read_text(encoding="utf-8")

    try:
        ticket = parse_ticket(raw)
    except TicketParseError as exc:
        click.echo(f"Ticket error: {exc}", err=True)
        sys.exit(1)

    click.echo(
        f"Parsed {ticket.key}: {ticket.summary}  "
        f"[{len(ticket.acceptance_criteria)} acceptance criteria, "
        f"{len(ticket.definition_of_done)} DOD]"
    )

    request = GenerateFromTicketRequest(
        ticket=ticket,
        framework=framework,
        output_file=output_file,  # type: ignore[arg-type]
        use_cache=not no_cache,
    )

    verified = None
    try:
        generator = TestGenerator(settings)
        if url:
            verified = generator.generate_and_verify_from_ticket(request, base_url=url)
            response = verified.response
        else:
            response = generator.generate_from_ticket(request)
    except ClaudeAPIError as exc:
        click.echo(f"Claude API error: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:
        logger.exception("Unexpected error during ticket generation")
        click.echo(f"Unexpected error: {exc}", err=True)
        sys.exit(3)

    _report_run(response, verified, quality_label="coverage")

    if not response.validation_passed:
        click.echo(
            "WARNING: coverage gate failed — fewer tests than criteria, or not traceable "
            "to the ticket key.",
            err=True,
        )

    if show_code:
        click.echo("\n" + "─" * 72)
        click.echo(response.generated_code)
        click.echo("─" * 72)


if __name__ == "__main__":
    cli()
