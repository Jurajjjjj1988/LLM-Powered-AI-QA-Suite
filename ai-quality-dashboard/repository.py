"""
Read-only repository layer for ai-quality-dashboard.

All queries use SQLAlchemy ORM.  No raw SQL strings.
The dashboard never writes — it only reads the DB populated by the other tools.

Why read-only queries here and not in app.py?
- Separation of concerns: app.py handles HTTP routing and serialisation;
  repository.py handles all database access.
- Easier to test in isolation without standing up FastAPI.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from common.models import FlakyTestResult, FlakyTestRun, GeneratedTest, HealedSelector
from common.schemas import DashboardSummary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def get_summary(session: Session) -> DashboardSummary:
    """Return aggregate metrics for the dashboard summary cards."""

    generated_count: int = session.query(func.count(GeneratedTest.id)).scalar() or 0

    flaky_runs_count: int = session.query(func.count(FlakyTestRun.id)).scalar() or 0

    avg_flaky_rate: float = (
        session.query(func.avg(FlakyTestResult.fail_rate)).scalar() or 0.0
    )

    healed_count: int = session.query(func.count(HealedSelector.id)).scalar() or 0

    # Last activity: latest created_at / analyzed_at / healed_at across all tables
    last_gen: datetime | None = session.query(func.max(GeneratedTest.created_at)).scalar()
    last_run: datetime | None = session.query(func.max(FlakyTestRun.analyzed_at)).scalar()
    last_heal: datetime | None = session.query(func.max(HealedSelector.healed_at)).scalar()

    candidates = [ts for ts in [last_gen, last_run, last_heal] if ts is not None]
    last_activity = max(candidates) if candidates else None

    return DashboardSummary(
        generated_tests_count=generated_count,
        flaky_runs_count=flaky_runs_count,
        avg_flaky_rate=round(avg_flaky_rate, 2),
        healed_selectors_count=healed_count,
        last_activity_at=last_activity,
    )


# ---------------------------------------------------------------------------
# Generated tests
# ---------------------------------------------------------------------------

def get_generated_tests(
    session: Session,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    rows = (
        session.query(GeneratedTest)
        .order_by(GeneratedTest.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "framework": r.framework,
            "requirement_text": r.requirement_text[:200],
            "tokens_used": r.tokens_used,
            "validation_passed": r.validation_passed,
            "output_file_path": r.output_file_path,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Flaky tests
# ---------------------------------------------------------------------------

def get_flaky_runs(
    session: Session,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    runs = (
        session.query(FlakyTestRun)
        .order_by(FlakyTestRun.analyzed_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    result = []
    for run in runs:
        result.append(
            {
                "id": run.id,
                "analyzed_at": run.analyzed_at.isoformat(),
                "source_file": run.source_file,
                "total_tests": run.total_tests,
                "flaky_count": run.flaky_count,
                "flaky_rate_pct": round(
                    (run.flaky_count / run.total_tests * 100) if run.total_tests else 0.0,
                    2,
                ),
                "results": [
                    {
                        "test_name": r.test_name,
                        "fail_rate": round(r.fail_rate, 2),
                        "total_runs": r.total_runs,
                        "avg_duration_seconds": round(r.avg_duration_seconds, 3),
                        "ai_suggestion": r.ai_suggestion,
                    }
                    for r in run.results
                ],
            }
        )
    return result


def get_flaky_trend(session: Session, days: int = 30) -> list[dict]:
    """
    Return daily flaky-rate data for the last *days* days.
    Each point: {date: "YYYY-MM-DD", avg_flaky_rate: float, run_count: int}
    """
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        session.query(
            func.date(FlakyTestRun.analyzed_at).label("day"),
            func.avg(
                func.cast(FlakyTestRun.flaky_count, float)
                / func.cast(func.nullif(FlakyTestRun.total_tests, 0), float)
                * 100
            ).label("avg_flaky_rate"),
            func.count(FlakyTestRun.id).label("run_count"),
        )
        .filter(FlakyTestRun.analyzed_at >= since)
        .group_by(func.date(FlakyTestRun.analyzed_at))
        .order_by(func.date(FlakyTestRun.analyzed_at))
        .all()
    )

    return [
        {
            "date": str(row.day),
            "avg_flaky_rate": round(float(row.avg_flaky_rate or 0), 2),
            "run_count": row.run_count,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Healed selectors
# ---------------------------------------------------------------------------

def get_healed_selectors(
    session: Session,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    rows = (
        session.query(HealedSelector)
        .order_by(HealedSelector.healed_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        {
            "id": r.id,
            "healed_at": r.healed_at.isoformat(),
            "description": r.description,
            "old_selector": r.old_selector,
            "new_selector": r.new_selector,
            "validation_passed": r.validation_passed,
            "applied_count": r.applied_count,
            "tokens_used": r.tokens_used,
        }
        for r in rows
    ]
