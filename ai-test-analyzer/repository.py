"""
Repository layer for ai-test-analyzer.

Persists FlakyTestRun (one per analysis session) and FlakyTestResult (one per
flaky test within that run) via SQLAlchemy ORM — no raw SQL strings.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from common.models import FlakyTestResult, FlakyTestRun
from common.schemas import FlakyTestDetail

logger = logging.getLogger(__name__)


def save_flaky_run(
    session: Session,
    *,
    source_file: str | None,
    total_tests: int,
    flaky_count: int,
    results: list[FlakyTestDetail],
    model_used: str | None = None,
    suggestion_tokens: int | None = None,
) -> FlakyTestRun:
    """
    Persist a FlakyTestRun and all its FlakyTestResult children.

    The session is flushed (not committed) — the caller's context manager
    (get_session) owns the commit boundary.  This keeps the repository layer
    free of transaction-management concerns.
    """
    run = FlakyTestRun(
        source_file=source_file,
        total_tests=total_tests,
        flaky_count=flaky_count,
    )
    session.add(run)
    session.flush()  # assigns run.id

    for detail in results:
        result_row = FlakyTestResult(
            run_id=run.id,
            test_name=detail.test_name,
            fail_rate=detail.fail_rate,
            total_runs=detail.total_runs,
            avg_duration_seconds=detail.avg_duration_seconds,
            ai_suggestion=detail.ai_suggestion,
            model_used=model_used,
            suggestion_tokens=suggestion_tokens,
        )
        session.add(result_row)

    session.flush()

    logger.info(
        "FlakyTestRun saved",
        extra={
            "run_id": run.id,
            "total_tests": total_tests,
            "flaky_count": flaky_count,
            "source_file": source_file,
        },
    )
    return run
