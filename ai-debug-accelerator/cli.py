"""
CLI entry-point pre AI Debug-Accelerator.

Usage:
  python3 cli.py analyze playwright-report.json
  python3 cli.py analyze results/report.json --output-dir ./debug-reports
  python3 cli.py analyze test-results.json --open
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


@click.group()
def cli() -> None:
    """AI Debug-Accelerator — skráti MTTR pri Playwright zlyhaní pomocou Claude."""


@cli.command("analyze")
@click.argument("report_file", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, writable=True),
    default=None,
    help="Kde uložiť ai_debug_report.md (default: adresár report súboru).",
)
@click.option(
    "--open",
    "open_report",
    is_flag=True,
    default=False,
    help="Otvor report v predvolenom editore po vygenerovaní.",
)
def analyze_cmd(report_file: str, output_dir: str | None, open_report: bool) -> None:
    """Analyzuj Playwright report a vygeneruj ai_debug_report.md."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from debugger import analyze

    click.echo(f"\nAnalyzujem: {report_file}")
    click.echo("Spúšťam SDET + Code Review agentov...\n")

    try:
        report_path = analyze(report_file, output_dir=output_dir)
    except FileNotFoundError as exc:
        click.echo(f"Chyba: {exc}", err=True)
        sys.exit(1)
    except RuntimeError as exc:
        click.echo(f"Konfiguračná chyba: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:
        logging.exception("Neočakávaná chyba")
        click.echo(f"Chyba: {exc}", err=True)
        sys.exit(3)

    click.echo(f"\nReport uložený: {report_path}")

    if open_report:
        subprocess.run(["open", report_path], check=False)


if __name__ == "__main__":
    cli()
