"""
Repository layer for ai-test-generator.

Responsibilities:
- Cache lookup by requirement SHA-256 hash (avoids redundant API calls)
- Persist GeneratedTest rows via SQLAlchemy ORM (no raw SQL)
- Write generated code to disk when an output path is supplied
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from common.models import GeneratedTest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache / read operations
# ---------------------------------------------------------------------------

def find_cached_test(
    session: Session,
    requirement_hash: str,
    framework: str,
) -> GeneratedTest | None:
    """
    Return the most recent GeneratedTest for the given hash+framework pair,
    or None if no cache entry exists.

    Only records with validation_passed=True are returned so that a previously
    failed generation does not block a fresh attempt.
    """
    result = (
        session.query(GeneratedTest)
        .filter_by(
            requirement_hash=requirement_hash,
            framework=framework,
            validation_passed=True,
        )
        .order_by(GeneratedTest.created_at.desc())
        .first()
    )
    if result:
        logger.info(
            "Cache hit for test generation",
            extra={
                "requirement_hash": requirement_hash,
                "framework": framework,
                "cached_id": result.id,
            },
        )
    return result


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def save_generated_test(
    session: Session,
    *,
    requirement_hash: str,
    framework: str,
    requirement_text: str,
    generated_code: str,
    model_used: str,
    tokens_used: int,
    validation_passed: bool,
    output_file_path: str | None = None,
) -> GeneratedTest:
    """
    Persist a new GeneratedTest record and return it.
    The caller is responsible for committing the session.
    """
    record = GeneratedTest(
        requirement_hash=requirement_hash,
        framework=framework,
        requirement_text=requirement_text,
        generated_code=generated_code,
        model_used=model_used,
        tokens_used=tokens_used,
        validation_passed=validation_passed,
        output_file_path=output_file_path,
    )
    session.add(record)
    session.flush()  # assigns PK without committing
    logger.info(
        "GeneratedTest saved",
        extra={
            "id": record.id,
            "framework": framework,
            "tokens_used": tokens_used,
            "validation_passed": validation_passed,
        },
    )
    return record


def write_code_to_file(code: str, output_path: Path) -> None:
    """
    Write *code* to *output_path*, creating parent directories as needed.
    Raises OSError on I/O failures (let callers handle/log).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(code, encoding="utf-8")
    logger.info(
        "Generated test written to file",
        extra={"output_path": str(output_path), "bytes": len(code.encode())},
    )
