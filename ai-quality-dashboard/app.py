"""
FastAPI application for ai-quality-dashboard.

Routes:
  GET  /                         → serves static/index.html
  GET  /api/metrics/summary      → DashboardSummary JSON
  GET  /api/generated-tests      → paginated list of GeneratedTest rows
  GET  /api/flaky-tests          → paginated list of FlakyTestRun rows (with results)
  GET  /api/flaky-tests/trend    → daily flaky-rate time series (last 30 days)
  GET  /api/healed-selectors     → paginated list of HealedSelector rows

Design decisions:
- Read-only DB access via get_readonly_session (no writes from the dashboard).
- Static files served directly by FastAPI's StaticFiles mount — no separate web
  server needed for development or single-host deployments.
- All DB errors surface as HTTP 503 rather than 500 to signal "service
  temporarily unavailable due to data store issue" (correct HTTP semantics).
"""
from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from common.config import get_settings
from common.database import get_readonly_session, init_db
from common.exceptions import DatabaseError
from common.logging_config import configure_logging
from common.schemas import DashboardSummary

from repository import (
    get_flaky_runs,
    get_flaky_trend,
    get_generated_tests,
    get_healed_selectors,
    get_summary,
)

logger = logging.getLogger(__name__)

settings = get_settings()
configure_logging(settings, tool_name="ai-quality-dashboard")
init_db(settings.db_path)

app = FastAPI(
    title="AI QA Quality Dashboard",
    description="Read-only metrics dashboard for the AI QA Suite.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    return FileResponse(str(_STATIC_DIR / "index.html"))


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/metrics/summary", response_model=DashboardSummary, tags=["metrics"])
async def metrics_summary() -> DashboardSummary:
    """Return aggregate summary metrics for the dashboard cards."""
    try:
        with get_readonly_session(settings.db_path) as session:
            return get_summary(session)
    except DatabaseError as exc:
        logger.exception("DB error fetching summary")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/generated-tests", tags=["generated-tests"])
async def list_generated_tests(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Return a paginated list of generated test records (most recent first)."""
    try:
        with get_readonly_session(settings.db_path) as session:
            return get_generated_tests(session, limit=limit, offset=offset)
    except DatabaseError as exc:
        logger.exception("DB error fetching generated tests")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/flaky-tests", tags=["flaky-tests"])
async def list_flaky_tests(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Return a paginated list of flaky-test analysis runs with per-test results."""
    try:
        with get_readonly_session(settings.db_path) as session:
            return get_flaky_runs(session, limit=limit, offset=offset)
    except DatabaseError as exc:
        logger.exception("DB error fetching flaky tests")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/flaky-tests/trend", tags=["flaky-tests"])
async def flaky_trend(
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict]:
    """Return daily average flaky-rate data for the last *days* days."""
    try:
        with get_readonly_session(settings.db_path) as session:
            return get_flaky_trend(session, days=days)
    except DatabaseError as exc:
        logger.exception("DB error fetching flaky trend")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/healed-selectors", tags=["healed-selectors"])
async def list_healed_selectors(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Return a paginated list of healed CSS selector records (most recent first)."""
    try:
        with get_readonly_session(settings.db_path) as session:
            return get_healed_selectors(session, limit=limit, offset=offset)
    except DatabaseError as exc:
        logger.exception("DB error fetching healed selectors")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
