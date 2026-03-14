"""
CLI entry-point pre AI Data Mock-Architect.

Usage:
  python3 cli.py generate swagger.json
  python3 cli.py generate https://petstore.swagger.io/v2/swagger.json
  python3 cli.py generate swagger.json --output-dir ./my-mocks
  python3 cli.py generate swagger.json --open
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
    """AI Data Mock-Architect — generátor GDPR-safe mock dát z OpenAPI schémy."""


@cli.command("generate")
@click.argument("spec_source")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, writable=True),
    default=".",
    show_default=True,
    help="Kde vytvoriť mocks/ adresár.",
)
@click.option(
    "--open",
    "open_dir",
    is_flag=True,
    default=False,
    help="Otvor mocks/ adresár po vygenerovaní.",
)
def generate_cmd(spec_source: str, output_dir: str, open_dir: bool) -> None:
    """
    Vygeneruj GDPR-safe mock dáta z OpenAPI/Swagger schémy.

    SPEC_SOURCE môže byť lokálny súbor (swagger.json) alebo URL.
    """
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from mock_architect import generate

    is_url = spec_source.startswith("http://") or spec_source.startswith("https://")
    source_type = "URL" if is_url else "súbor"

    if not is_url and not Path(spec_source).exists():
        click.echo(f"Chyba: súbor '{spec_source}' neexistuje.", err=True)
        sys.exit(1)

    click.echo(f"\nZdroj schémy ({source_type}): {spec_source}")
    click.echo("Spúšťam Architect + SDET + Security agentov...\n")

    try:
        mocks_dir = generate(spec_source, output_dir=output_dir)
    except RuntimeError as exc:
        click.echo(f"Konfiguračná chyba: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:
        logging.exception("Neočakávaná chyba")
        click.echo(f"Chyba: {exc}", err=True)
        sys.exit(3)

    click.echo(f"\nMock súbory uložené: {mocks_dir}")
    click.echo("Formát kompatibilný s Prism a Mockoon.")

    if open_dir:
        subprocess.run(["open", mocks_dir], check=False)


if __name__ == "__main__":
    cli()
