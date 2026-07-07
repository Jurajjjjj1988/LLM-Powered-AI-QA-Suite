"""Command-line entry point for ai-quality-dashboard."""

from __future__ import annotations

import click

from ai_quality_dashboard.app import run


@click.group()
def cli() -> None:
    """AI Quality Dashboard — a read-only web view over the AI QA Suite's metrics."""


@cli.command()
def serve() -> None:
    """Start the dashboard web server (uvicorn)."""
    run()


if __name__ == "__main__":
    cli()
