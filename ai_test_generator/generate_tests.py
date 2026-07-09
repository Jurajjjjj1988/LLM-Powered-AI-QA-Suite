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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_test_generator.prompts import (
    SYSTEM_PROMPT,
    build_repair_message,
    build_ticket_user_message,
    build_user_message,
)
from ai_test_generator.repository import (
    find_cached_test,
    save_generated_test,
    write_code_to_file,
)
from ai_test_generator.validator import (
    ValidationResult,
    validate_generated_code,
    validate_ticket_coverage,
)
from common.claude_client import ClaudeClient
from common.config import Settings, get_settings
from common.database import get_session, init_db
from common.exceptions import ClaudeAPIError
from common.sanitizer import hash_text, sanitize_requirement
from common.schemas import (
    GenerateFromTicketRequest,
    GenerateTestsRequest,
    GenerateTestsResponse,
)
from common.test_runner import run_playwright_test

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifiedGeneration:
    """Result of the closed loop: the generation + whether it actually ran green."""

    response: GenerateTestsResponse
    execution_passed: bool | None  # None = not run (no base_url given → open-loop)
    repair_attempts: int
    run_output: str


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
        Generate (or retrieve cached) tests for a free-text requirement.

        Returns GenerateTestsResponse with generated code, token usage,
        validation status, and whether the result came from cache.
        """
        clean_requirement = sanitize_requirement(request.requirement)
        user_message = build_user_message(request.framework, clean_requirement)
        return self._run_generation(
            user_message=user_message,
            cache_text=clean_requirement + request.framework,
            requirement_text=clean_requirement,
            framework=request.framework,
            output_file=request.output_file,
            use_cache=request.use_cache,
        )

    def generate_from_ticket(self, request: GenerateFromTicketRequest) -> GenerateTestsResponse:
        """Generate tests FROM a structured ticket — one traceable test per criterion.

        This is the tool's real contract: the ticket's acceptance criteria are the
        source of truth, not a vague one-liner. On top of the standard structural
        validation it applies a coverage gate, so a generation with fewer tests than
        criteria (or one that doesn't reference the ticket key) is marked invalid.
        """
        ticket = request.ticket
        user_message = build_ticket_user_message(
            key=ticket.key,
            summary=ticket.summary,
            description=ticket.description,
            acceptance_criteria=ticket.acceptance_criteria,
            definition_of_done=ticket.definition_of_done,
            framework=request.framework,
        )
        # Delimited so two different tickets can't hash to the same key by concatenation
        # (\x1f between fields, \x1e between list items — control chars the parser strips).
        cache_text = (
            f"{ticket.key}\x1f"
            + "\x1e".join(ticket.acceptance_criteria)
            + "\x1f"
            + "\x1e".join(ticket.definition_of_done)
            + f"\x1f{request.framework}"
        )

        def _coverage(code: str, framework: str) -> ValidationResult:
            return validate_ticket_coverage(
                code, framework, len(ticket.acceptance_criteria), ticket.key
            )

        return self._run_generation(
            user_message=user_message,
            cache_text=cache_text,
            requirement_text=f"[{ticket.key}] {ticket.summary}",
            framework=request.framework,
            output_file=request.output_file,
            use_cache=request.use_cache,
            extra_validation=_coverage,
        )

    def _run_generation(
        self,
        *,
        user_message: str,
        cache_text: str,
        requirement_text: str,
        framework: str,
        output_file: Path | None,
        use_cache: bool,
        extra_validation: Callable[[str, str], ValidationResult] | None = None,
    ) -> GenerateTestsResponse:
        """Shared pipeline: cache → Claude → validate → (extra gate) → write → persist.

        Both the free-text and ticket paths funnel through here; they differ only in
        the prompt, the cache key, and an optional extra validation gate (coverage).
        """
        req_hash = hash_text(cache_text)

        if use_cache:
            with get_session(self._settings.db_path) as session:
                cached = find_cached_test(session, req_hash, framework)
                if cached:
                    logger.info(
                        "Returning cached test",
                        extra={"id": cached.id, "framework": framework},
                    )
                    # The cached output path may be stale (a different/earlier run). If a
                    # file is requested now, (re)write it so a following closed-loop run
                    # has a real spec to execute.
                    out_path = cached.output_file_path
                    if output_file is not None:
                        write_code_to_file(cached.generated_code, Path(output_file))
                        out_path = str(Path(output_file).resolve())
                    return GenerateTestsResponse(
                        id=cached.id,
                        generated_code=cached.generated_code,
                        tokens_used=cached.tokens_used,
                        validation_passed=cached.validation_passed,
                        output_file_path=out_path,
                        from_cache=True,
                    )

        # User content never enters the system prompt (prompt-injection defence).
        logger.info(
            "Calling Claude for test generation",
            extra={"framework": framework, "req_hash": req_hash},
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

        # Validate: structural first, then the optional coverage gate (only if structural passed)
        validation_result = validate_generated_code(generated_code, framework)
        if validation_result.passed and extra_validation is not None:
            validation_result = extra_validation(generated_code, framework)
        if not validation_result.passed:
            logger.warning(
                "Validation failed for generated code",
                extra={"reasons": validation_result.reasons},
            )
            # Persist anyway with validation_passed=False so the failure is visible.

        # Optionally write to file
        output_file_str: str | None = None
        if output_file is not None:
            output_path = Path(output_file)
            try:
                write_code_to_file(generated_code, output_path)
                output_file_str = str(output_path.resolve())
            except OSError:
                logger.exception(
                    "Failed to write generated code to file",
                    extra={"output_file": str(output_file)},
                )
                # Non-fatal: we still persist to DB and return the code

        # Persist to DB
        with get_session(self._settings.db_path) as session:
            record = save_generated_test(
                session,
                requirement_hash=req_hash,
                framework=framework,
                requirement_text=requirement_text,
                generated_code=generated_code,
                model_used=self._settings.claude_model,
                tokens_used=tokens_used,
                validation_passed=validation_result.passed,
                output_file_path=output_file_str,
            )
            record_id = record.id

        return GenerateTestsResponse(
            id=record_id,
            generated_code=generated_code,
            tokens_used=tokens_used,
            validation_passed=validation_result.passed,
            output_file_path=output_file_str,
            from_cache=False,
        )

    def generate_and_verify(
        self,
        request: GenerateTestsRequest,
        base_url: str | None = None,
        max_repairs: int = 2,
    ) -> VerifiedGeneration:
        """Closed loop for a free-text requirement: generate → RUN → repair until green."""
        response = self.generate(request)
        return self._verify_and_repair(response, request.framework, base_url, max_repairs)

    def generate_and_verify_from_ticket(
        self,
        request: GenerateFromTicketRequest,
        base_url: str | None = None,
        max_repairs: int = 2,
    ) -> VerifiedGeneration:
        """Closed loop for a ticket: generate tests from criteria → RUN → repair until green.

        The full-fidelity path: acceptance criteria in, a suite that actually passes
        against a live app out.
        """
        response = self.generate_from_ticket(request)
        return self._verify_and_repair(response, request.framework, base_url, max_repairs)

    def _verify_and_repair(
        self,
        response: GenerateTestsResponse,
        framework: str,
        base_url: str | None,
        max_repairs: int,
    ) -> VerifiedGeneration:
        """Run the generated spec and repair on a red run until green (the shared loop).

        Without a base_url (or when no output_file was written) it stays open-loop and
        returns execution_passed=None. With one, it runs the spec, and on a red run
        feeds the failure back to the model to repair, up to *max_repairs* times,
        accepting only a genuinely green run.
        """
        if base_url is None or response.output_file_path is None:
            return VerifiedGeneration(
                response=response, execution_passed=None, repair_attempts=0, run_output=""
            )
        if framework.lower() != "playwright":
            # The runner drives `npx playwright test`; it can't execute cypress/selenium.
            logger.warning(
                "Closed-loop run skipped — the runner supports Playwright only",
                extra={"framework": framework},
            )
            return VerifiedGeneration(
                response=response, execution_passed=None, repair_attempts=0, run_output=""
            )

        spec_path = Path(response.output_file_path)
        current_code = response.generated_code
        run_output = ""
        for attempt in range(max_repairs + 1):
            result = run_playwright_test(spec_path, base_url)
            run_output = result.output
            if result.passed:
                return VerifiedGeneration(
                    response=response,
                    execution_passed=True,
                    repair_attempts=attempt,
                    run_output=run_output,
                )
            if attempt == max_repairs:
                break
            repair_message = build_repair_message(framework, current_code, result.output)
            try:
                repaired, _ = self._client.complete(
                    system_prompt=SYSTEM_PROMPT,
                    user_message=repair_message,
                    max_tokens=self._settings.claude_max_tokens,
                )
            except ClaudeAPIError:
                logger.exception("Claude repair call failed")
                break
            current_code = _strip_code_fences(repaired)
            write_code_to_file(current_code, spec_path)

        return VerifiedGeneration(
            response=response,
            execution_passed=False,
            repair_attempts=max_repairs,
            run_output=run_output,
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
