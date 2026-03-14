"""
Click CLI entry-point for ai-test-healer.

Usage examples:
  python cli.py heal "Login button" "button.login" "<button class='btn-submit login-button'>Login</button>"
  python cli.py heal "Email input" "input.email" --html-file page_fragment.html
  python cli.py heal "Submit button" "#submit" "<form>...</form>" --force
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from common.config import get_settings
from common.exceptions import ClaudeAPIError, SanitizationError
from common.logging_config import configure_logging
from common.schemas import HealSelectorRequest

from healer import SelfHealingEngine

logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """AI Self-Healing Engine — repair broken CSS selectors using Claude."""


@cli.command("heal")
@click.argument("description")
@click.argument("old_selector")
@click.argument("html_snippet", required=False, default=None)
@click.option(
    "--html-file",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    default=None,
    help="Read HTML snippet from a file instead of passing it inline.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Bypass cache and always call Claude.",
)
def heal_cmd(
    description: str,
    old_selector: str,
    html_snippet: str | None,
    html_file: str | None,
    force: bool,
) -> None:
    """
    Repair OLD_SELECTOR for the element described by DESCRIPTION.

    HTML_SNIPPET can be provided as an inline argument or via --html-file.
    At least one of the two must be supplied.
    """
    settings = get_settings()
    configure_logging(settings, tool_name="ai-test-healer")

    # Resolve HTML source
    if html_file:
        try:
            html_content = Path(html_file).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            click.echo(f"Failed to read HTML file: {exc}", err=True)
            sys.exit(1)
    elif html_snippet:
        html_content = html_snippet
    else:
        click.echo(
            "Error: provide HTML_SNIPPET as a positional argument or via --html-file.",
            err=True,
        )
        sys.exit(1)

    request = HealSelectorRequest(
        description=description,
        old_selector=old_selector,
        html_snippet=html_content,
        force_heal=force,
    )

    try:
        engine = SelfHealingEngine(settings)
        response = engine.heal(request)
    except SanitizationError as exc:
        click.echo(f"Input error: {exc}", err=True)
        sys.exit(1)
    except ClaudeAPIError as exc:
        click.echo(f"Claude API error: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:
        logger.exception("Unexpected error during healing")
        click.echo(f"Unexpected error: {exc}", err=True)
        sys.exit(3)

    # --- Report ---
    source = "cache" if response.from_cache else "Claude API"
    valid = "PASSED" if response.validation_passed else "FAILED"

    click.echo(f"\nHealing complete  [source={source}  validation={valid}  tokens={response.tokens_used}  id={response.id}]")
    click.echo(f"  Old selector : {old_selector}")
    click.echo(f"  New selector : {response.new_selector}")

    if not response.validation_passed:
        click.echo(
            "WARNING: the returned selector did not pass CSS validation. "
            "Use it with caution.",
            err=True,
        )

    if response.new_selector == "NONE":
        click.echo(
            "Claude could not find a replacement selector in the provided HTML.",
            err=True,
        )
        sys.exit(4)


if __name__ == "__main__":
    cli()
