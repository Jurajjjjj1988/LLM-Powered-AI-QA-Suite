"""
Repository layer for ai-test-healer.

Responsibilities:
- Cache lookup: same old_selector + html_context_hash → return existing record
  and increment applied_count (zero API calls on hit)
- Persist new HealedSelector rows via SQLAlchemy ORM (no raw SQL)
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from common.models import HealedSelector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache / read operations
# ---------------------------------------------------------------------------

def find_cached_selector(
    session: Session,
    old_selector: str,
    html_context_hash: str,
) -> HealedSelector | None:
    """
    Return a cached HealedSelector for the given (old_selector, html_context_hash)
    pair, or None if no cache entry exists.

    Why both fields?
    - The same broken selector in a DIFFERENT HTML context may need a different
      fix, so the hash of the surrounding HTML is part of the cache key.
    - We return the most recently healed record to surface any updated selectors.
    """
    result = (
        session.query(HealedSelector)
        .filter_by(
            old_selector=old_selector,
            html_context_hash=html_context_hash,
        )
        .order_by(HealedSelector.healed_at.desc())
        .first()
    )
    if result:
        logger.info(
            "Cache hit for selector healing",
            extra={
                "old_selector": old_selector,
                "html_context_hash": html_context_hash,
                "cached_id": result.id,
                "applied_count": result.applied_count,
            },
        )
    return result


def increment_applied_count(session: Session, record: HealedSelector) -> None:
    """
    Increment the applied_count on an existing HealedSelector record.
    Caller's session context manager owns the commit.
    """
    record.applied_count += 1
    session.flush()
    logger.debug(
        "applied_count incremented",
        extra={"id": record.id, "applied_count": record.applied_count},
    )


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def save_healed_selector(
    session: Session,
    *,
    description: str,
    old_selector: str,
    new_selector: str,
    html_context_hash: str,
    model_used: str,
    tokens_used: int,
    validation_passed: bool,
) -> HealedSelector:
    """
    Persist a new HealedSelector record and return it.
    The caller's context manager owns the commit.
    """
    record = HealedSelector(
        description=description,
        old_selector=old_selector,
        new_selector=new_selector,
        html_context_hash=html_context_hash,
        model_used=model_used,
        tokens_used=tokens_used,
        validation_passed=validation_passed,
        applied_count=1,  # First use counts as applied
    )
    session.add(record)
    session.flush()

    logger.info(
        "HealedSelector saved",
        extra={
            "id": record.id,
            "old_selector": old_selector,
            "new_selector": new_selector,
            "validation_passed": validation_passed,
        },
    )
    return record
