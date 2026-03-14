"""
Click CLI entry-point for ai-test-generator.

Usage examples:
  python cli.py generate "User can log in with valid credentials" --framework playwright
  python cli.py generate "..." --framework cypress --output-file ./out/login.spec.ts
  python cli.py generate "..." --no-cache
"""
from __future__ import annotations

import sys
import logging

import click

from common.config import get_settings
from common.exceptions import ClaudeAPIError, SanitizationError
from common.logging_config import configure_logging
from common.schemas import GenerateTestsRequest

from generate_tests import TestGenerator

logger = logging.getLogger(__name__)


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
def generate_cmd(
    requirement: str,
    framework: str,
    output_file: str | None,
    no_cache: bool,
    show_code: bool,
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

    try:
        generator = TestGenerator(settings)
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

    # Summary
    source = "cache" if response.from_cache else "Claude API"
    valid = "PASSED" if response.validation_passed else "FAILED"
    click.echo(f"\nGeneration complete  [source={source}  validation={valid}  tokens={response.tokens_used}  id={response.id}]")

    if response.output_file_path:
        click.echo(f"Written to: {response.output_file_path}")

    if not response.validation_passed:
        click.echo(
            "WARNING: validation failed — the generated code may not be runnable.",
            err=True,
        )

    if show_code:
        click.echo("\n" + "─" * 72)
        click.echo(response.generated_code)
        click.echo("─" * 72)


if __name__ == "__main__":
    cli()
