"""
Main TestGenerator orchestration class for ai-test-generator.

Orchestration flow:
  1. Sanitize input
  2. Hash requirement → cache lookup
  3. Build prompts (system static / user dynamic)
  4. Call Claude
  5. Validate output
  6. Persist to DB
  7. Optionally write to file
  8. Return GenerateTestsResponse
"""
from __future__ import annotations

import logging
from pathlib import Path

from common.claude_client import ClaudeClient
from common.config import Settings, get_settings
from common.database import get_session, init_db
from common.exceptions import ClaudeAPIError
from common.sanitizer import hash_text, sanitize_requirement
from common.schemas import GenerateTestsRequest, GenerateTestsResponse

from prompts import SYSTEM_PROMPT, build_user_message
from repository import (
    find_cached_test,
    save_generated_test,
    write_code_to_file,
)
from validator import validate_generated_code

logger = logging.getLogger(__name__)


class TestGenerator:
    """
    High-level orchestrator for AI-driven test generation.

    Why a class?
    - Holds initialised dependencies (settings, Claude client) across multiple
      calls without re-reading env vars or re-connecting on every invocation.
    - Makes unit testing trivial: inject a mock ClaudeClient via constructor.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = ClaudeClient(self._settings)
        init_db(self._settings.db_path)
        logger.info(
            "TestGenerator initialised",
            extra={
                "model": self._settings.claude_model,
                "db_path": str(self._settings.db_path),
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, request: GenerateTestsRequest) -> GenerateTestsResponse:
        """
        Generate (or retrieve cached) tests for the given request.

        Returns GenerateTestsResponse with generated code, token usage,
        validation status, and whether the result came from cache.
        """
        # 1. Sanitize
        clean_requirement = sanitize_requirement(request.requirement)

        # 2. Hash + optional cache check
        req_hash = hash_text(clean_requirement + request.framework)

        if request.use_cache:
            with get_session(self._settings.db_path) as session:
                cached = find_cached_test(session, req_hash, request.framework)
                if cached:
                    logger.info(
                        "Returning cached test",
                        extra={"id": cached.id, "framework": request.framework},
                    )
                    return GenerateTestsResponse(
                        id=cached.id,
                        generated_code=cached.generated_code,
                        tokens_used=cached.tokens_used,
                        validation_passed=cached.validation_passed,
                        output_file_path=cached.output_file_path,
                        from_cache=True,
                    )

        # 3. Build prompts  (user content never enters system prompt)
        user_message = build_user_message(request.framework, clean_requirement)

        # 4. Call Claude
        logger.info(
            "Calling Claude for test generation",
            extra={"framework": request.framework, "req_hash": req_hash},
        )
        try:
            generated_code, tokens_used = self._client.complete(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_message,
                max_tokens=self._settings.claude_max_tokens,
            )
        except ClaudeAPIError:
            logger.exception("Claude API call failed during test generation")
            raise

        # Strip accidental markdown fences that the model sometimes emits
        generated_code = _strip_code_fences(generated_code)

        # 5. Validate
        validation_result = validate_generated_code(generated_code, request.framework)
        if not validation_result.passed:
            logger.warning(
                "Validation failed for generated code",
                extra={"reasons": validation_result.reasons},
            )
            # We persist anyway with validation_passed=False so the failure
            # is visible in the DB; callers may choose to surface the reasons.

        # 6. Optionally write to file
        output_file_str: str | None = None
        if request.output_file is not None:
            output_path = Path(request.output_file)
            try:
                write_code_to_file(generated_code, output_path)
                output_file_str = str(output_path.resolve())
            except OSError:
                logger.exception(
                    "Failed to write generated code to file",
                    extra={"output_file": str(request.output_file)},
                )
                # Non-fatal: we still persist to DB and return the code

        # 7. Persist to DB
        with get_session(self._settings.db_path) as session:
            record = save_generated_test(
                session,
                requirement_hash=req_hash,
                framework=request.framework,
                requirement_text=clean_requirement,
                generated_code=generated_code,
                model_used=self._settings.claude_model,
                tokens_used=tokens_used,
                validation_passed=validation_result.passed,
                output_file_path=output_file_str,
            )
            record_id = record.id

        # 8. Return
        return GenerateTestsResponse(
            id=record_id,
            generated_code=generated_code,
            tokens_used=tokens_used,
            validation_passed=validation_result.passed,
            output_file_path=output_file_str,
            from_cache=False,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_code_fences(text: str) -> str:
    """
    Remove triple-backtick markdown code fences if the model included them.
    Handles ```typescript, ```python, ``` etc.
    """
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
