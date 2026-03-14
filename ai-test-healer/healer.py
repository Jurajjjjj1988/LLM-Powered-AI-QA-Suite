"""
Main SelfHealingEngine orchestration class for ai-test-healer.

Orchestration flow:
  1. Sanitize inputs (selector + HTML)
  2. Hash HTML snippet → DB cache lookup (old_selector + html_hash)
  3. Cache hit  → increment applied_count, return cached result
  4. Cache miss → build prompts, call Claude
  5. Parse Claude response (must be a single selector or "NONE")
  6. Validate CSS syntax via cssselect
  7. Persist HealedSelector (validation_passed may be False — still persisted)
  8. Return HealSelectorResponse

Key design decision — return even invalid selectors with a warning:
  The requirement says "save with validation_passed=False, return the selector
  anyway with warning".  This is intentional: an invalid selector from Claude
  is still potentially useful diagnostic info for the engineer.  The caller
  sees the warning via response.validation_passed=False.
"""
from __future__ import annotations

import logging

from common.claude_client import ClaudeClient
from common.config import Settings, get_settings
from common.database import get_session, init_db
from common.exceptions import ClaudeAPIError, SanitizationError
from common.sanitizer import hash_text, sanitize_html_snippet, sanitize_selector
from common.schemas import HealSelectorRequest, HealSelectorResponse

from prompts import SYSTEM_PROMPT, build_heal_user_message
from repository import (
    find_cached_selector,
    increment_applied_count,
    save_healed_selector,
)
from selector_validator import validate_css_selector

logger = logging.getLogger(__name__)

# Token budget: healing needs only a short response (one selector)
_HEAL_MAX_TOKENS = 128


class SelfHealingEngine:
    """
    Orchestrates CSS selector repair using Claude as the AI backend.

    Caching strategy: (old_selector, sha256(html_snippet)) is the cache key.
    The same broken selector applied to different HTML contexts may need
    different fixes, so the HTML hash is part of the key.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ClaudeClient(self._settings)
        init_db(self._settings.db_path)
        logger.info(
            "SelfHealingEngine initialised",
            extra={"model": self._settings.claude_model},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def heal(self, request: HealSelectorRequest) -> HealSelectorResponse:
        """
        Repair the broken selector in *request* and return the replacement.

        If force_heal=True the cache is bypassed entirely.
        """
        # 1. Sanitize
        try:
            clean_old_selector = sanitize_selector(request.old_selector)
        except SanitizationError:
            # Old selector may have chars outside the allowlist (it's broken
            # after all).  Log the warning but do not abort — we still want to
            # attempt healing; we just skip sanitization enforcement here.
            clean_old_selector = request.old_selector.strip()[:500]
            logger.warning(
                "Old selector failed sanitization; proceeding with truncated value",
                extra={"old_selector": clean_old_selector},
            )

        clean_html = sanitize_html_snippet(request.html_snippet)
        html_hash = hash_text(clean_html)

        # 2. Cache lookup (unless force_heal)
        if not request.force_heal:
            with get_session(self._settings.db_path) as session:
                cached = find_cached_selector(session, clean_old_selector, html_hash)
                if cached:
                    increment_applied_count(session, cached)
                    return HealSelectorResponse(
                        id=cached.id,
                        new_selector=cached.new_selector,
                        validation_passed=cached.validation_passed,
                        from_cache=True,
                        tokens_used=0,
                    )

        # 3. Build prompts and call Claude
        user_message = build_heal_user_message(
            description=request.description,
            old_selector=clean_old_selector,
            html_snippet=clean_html,
        )

        logger.info(
            "Calling Claude for selector healing",
            extra={
                "old_selector": clean_old_selector,
                "html_hash": html_hash,
                "force_heal": request.force_heal,
            },
        )

        try:
            raw_response, tokens_used = self._client.complete(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_message,
                max_tokens=_HEAL_MAX_TOKENS,
            )
        except ClaudeAPIError:
            logger.exception("Claude API call failed during selector healing")
            raise

        # 4. Parse Claude response
        new_selector = _extract_selector(raw_response)

        if new_selector.upper() == "NONE":
            logger.warning(
                "Claude could not find a replacement selector",
                extra={"old_selector": clean_old_selector, "description": request.description},
            )
            # Persist the NONE result so it's visible in the dashboard
            with get_session(self._settings.db_path) as session:
                record = save_healed_selector(
                    session,
                    description=request.description,
                    old_selector=clean_old_selector,
                    new_selector="NONE",
                    html_context_hash=html_hash,
                    model_used=self._settings.claude_model,
                    tokens_used=tokens_used,
                    validation_passed=False,
                )
            return HealSelectorResponse(
                id=record.id,
                new_selector="NONE",
                validation_passed=False,
                from_cache=False,
                tokens_used=tokens_used,
            )

        # 5. Validate
        validation_result = validate_css_selector(new_selector)
        if not validation_result.valid:
            logger.warning(
                "Healed selector failed CSS validation — persisting with validation_passed=False",
                extra={
                    "new_selector": new_selector,
                    "reason": validation_result.reason,
                },
            )

        # 6. Persist
        with get_session(self._settings.db_path) as session:
            record = save_healed_selector(
                session,
                description=request.description,
                old_selector=clean_old_selector,
                new_selector=new_selector,
                html_context_hash=html_hash,
                model_used=self._settings.claude_model,
                tokens_used=tokens_used,
                validation_passed=validation_result.valid,
            )
            record_id = record.id

        return HealSelectorResponse(
            id=record_id,
            new_selector=new_selector,
            validation_passed=validation_result.valid,
            from_cache=False,
            tokens_used=tokens_used,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_selector(raw: str) -> str:
    """
    Clean Claude's raw response down to a single selector string.

    The system prompt instructs the model to return only a selector, but
    defensive stripping handles edge cases like surrounding whitespace,
    backticks, or a leading/trailing newline.
    """
    text = raw.strip()

    # Strip backtick quoting if present (e.g., `button.submit`)
    if text.startswith("`") and text.endswith("`"):
        text = text[1:-1].strip()

    # Strip single or double quote wrapping
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        text = text[1:-1].strip()

    # If the model still gave multiple lines, take only the first non-empty one
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped

    return "NONE"
