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
- **Import side-effect-free.** Settings/logging/DB init run in a FastAPI `lifespan`
  at startup, never at import — so the module is importable + testable offline.
- **Sessions via dependency injection.** Routes receive a read-only session from
  `Depends(get_db_session)`; tests override that dependency with an in-memory DB
  (`app.dependency_overrides`) instead of reloading the module.
- All DB errors (connect or query) surface as HTTP 503 (correct "data store
  temporarily unavailable" semantics), mapped once in the dependency.
- Static files served directly by FastAPI's StaticFiles mount.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from ai_quality_dashboard.repository import (
    get_flaky_runs,
    get_flaky_trend,
    get_generated_tests,
    get_healed_selectors,
    get_summary,
)
from common.config import get_settings
from common.database import get_readonly_session, init_db
from common.exceptions import DatabaseError
from common.logging_config import configure_logging
from common.schemas import DashboardSummary

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Configure logging + initialise the DB at startup (not at import)."""
    settings = get_settings()
    configure_logging(settings, tool_name="ai-quality-dashboard")
    init_db(settings.db_path)
    yield


def get_db_session() -> Generator[Session, None, None]:
    """Yield a read-only DB session; map any DatabaseError (connect or query) to 503.

    Tests override this via ``app.dependency_overrides[get_db_session]`` to inject
    an in-memory session, so no real DB or settings are needed under test.
    """
    settings = get_settings()
    try:
        with get_readonly_session(settings.db_path) as session:
            yield session
    except DatabaseError as exc:
        logger.exception("DB error serving dashboard request")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


app = FastAPI(
    title="AI QA Quality Dashboard",
    description="Read-only metrics dashboard for the AI QA Suite.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
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
async def metrics_summary(session: Session = Depends(get_db_session)) -> DashboardSummary:
    """Return aggregate summary metrics for the dashboard cards."""
    return get_summary(session)


@app.get("/api/generated-tests", tags=["generated-tests"])
async def list_generated_tests(
    session: Session = Depends(get_db_session),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Return a paginated list of generated test records (most recent first)."""
    return get_generated_tests(session, limit=limit, offset=offset)


@app.get("/api/flaky-tests", tags=["flaky-tests"])
async def list_flaky_tests(
    session: Session = Depends(get_db_session),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Return a paginated list of flaky-test analysis runs with per-test results."""
    return get_flaky_runs(session, limit=limit, offset=offset)


@app.get("/api/flaky-tests/trend", tags=["flaky-tests"])
async def flaky_trend(
    session: Session = Depends(get_db_session),
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict]:
    """Return daily average flaky-rate data for the last *days* days."""
    return get_flaky_trend(session, days=days)


@app.get("/api/healed-selectors", tags=["healed-selectors"])
async def list_healed_selectors(
    session: Session = Depends(get_db_session),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Return a paginated list of healed CSS selector records (most recent first)."""
    return get_healed_selectors(session, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------


def run() -> None:
    """Start the dashboard with uvicorn (used by the ai-quality-dashboard CLI)."""
    settings = get_settings()
    uvicorn.run(
        "ai_quality_dashboard.app:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
