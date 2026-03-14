from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

import anthropic
from pydantic import BaseModel
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from common.exceptions import ClaudeAPIError

if TYPE_CHECKING:
    from common.config import Settings

logger = logging.getLogger(__name__)

# Models that support adaptive thinking (no budget_tokens needed)
_ADAPTIVE_THINKING_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6"}

# Stream responses above this threshold to avoid HTTP timeouts on large outputs
_STREAM_THRESHOLD_TOKENS = 1024

_M = TypeVar("_M", bound=BaseModel)


class ClaudeClient:
    def __init__(self, settings: Settings) -> None:
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.claude_timeout_seconds,
        )
        self._model = settings.claude_model
        self._default_max_tokens = settings.claude_max_tokens
        self._settings = settings
        self._use_adaptive_thinking = self._model in _ADAPTIVE_THINKING_MODELS

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int | None = None,
    ) -> tuple[str, int]:
        """
        Call Claude with separate system and user messages.
        Returns (response_text, tokens_used).

        - Uses adaptive thinking for Opus 4.6 / Sonnet 4.6.
        - Streams responses above _STREAM_THRESHOLD_TOKENS to prevent timeouts.
        - Retries on rate limits, timeouts, and server errors.

        Raises ClaudeAPIError on final failure after retries.
        """
        return self._complete_with_retry(system_prompt, user_message, max_tokens)

    def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        output_schema: type[_M],
        max_tokens: int | None = None,
    ) -> tuple[_M, int]:
        """
        Call Claude and parse the response into *output_schema* (a Pydantic model).
        Uses `client.messages.parse()` for guaranteed schema-valid output.
        Returns (parsed_model_instance, tokens_used).
        Raises ClaudeAPIError on API failure or schema validation error.
        """
        effective_max_tokens = max_tokens or self._default_max_tokens

        @retry(
            stop=stop_after_attempt(self._settings.retry_max_attempts),
            wait=wait_exponential_jitter(
                initial=self._settings.retry_wait_min_seconds,
                max=self._settings.retry_wait_max_seconds,
            ),
            retry=retry_if_exception_type(
                (
                    anthropic.RateLimitError,
                    anthropic.APITimeoutError,
                    anthropic.InternalServerError,
                )
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _call() -> tuple[_M, int]:
            kwargs: dict = dict(
                model=self._model,
                max_tokens=effective_max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                output_format=output_schema,
            )
            # Adaptive thinking is incompatible with structured outputs —
            # the model cannot simultaneously reason freely and follow a strict
            # JSON schema. Omit thinking here.
            try:
                response = self._client.messages.parse(**kwargs)
            except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.InternalServerError):
                raise
            except anthropic.APIError as exc:
                raise ClaudeAPIError(f"Claude API error: {exc}") from exc

            if response.parsed_output is None:
                raise ClaudeAPIError(
                    "Structured output parsing returned None — "
                    f"stop_reason={response.stop_reason}"
                )
            tokens = response.usage.input_tokens + response.usage.output_tokens
            logger.debug(
                "Claude structured response received",
                extra={"tokens": tokens, "model": self._model},
            )
            return response.parsed_output, tokens  # type: ignore[return-value]

        try:
            return _call()
        except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.InternalServerError) as exc:
            raise ClaudeAPIError(f"Claude API failed after retries: {exc}") from exc

    def _complete_with_retry(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int | None,
    ) -> tuple[str, int]:
        effective_max_tokens = max_tokens or self._default_max_tokens

        @retry(
            stop=stop_after_attempt(self._settings.retry_max_attempts),
            wait=wait_exponential_jitter(
                initial=self._settings.retry_wait_min_seconds,
                max=self._settings.retry_wait_max_seconds,
            ),
            retry=retry_if_exception_type(
                (
                    anthropic.RateLimitError,
                    anthropic.APITimeoutError,
                    anthropic.InternalServerError,
                )
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _call() -> tuple[str, int]:
            kwargs: dict = dict(
                model=self._model,
                max_tokens=effective_max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            if self._use_adaptive_thinking:
                kwargs["thinking"] = {"type": "adaptive"}

            try:
                if effective_max_tokens >= _STREAM_THRESHOLD_TOKENS:
                    with self._client.messages.stream(**kwargs) as stream:
                        final = stream.get_final_message()
                else:
                    final = self._client.messages.create(**kwargs)
            except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.InternalServerError):
                raise
            except anthropic.APIError as exc:
                raise ClaudeAPIError(f"Claude API error: {exc}") from exc

            # Skip thinking blocks — extract text only
            text = next(
                (block.text for block in final.content if block.type == "text"),
                "",
            )
            tokens = final.usage.input_tokens + final.usage.output_tokens
            logger.debug(
                "Claude response received",
                extra={"tokens": tokens, "model": self._model},
            )
            return text, tokens

        try:
            return _call()
        except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.InternalServerError) as exc:
            raise ClaudeAPIError(f"Claude API failed after retries: {exc}") from exc
