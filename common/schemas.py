from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GenerateTestsRequest(BaseModel):
    requirement: str = Field(..., min_length=10, max_length=5000)
    framework: Literal["playwright", "cypress", "selenium"] = "playwright"
    output_file: Path | None = None
    use_cache: bool = True


class JiraTicket(BaseModel):
    """A work item (Jira issue / GitHub issue) as the source of truth for tests.

    The tool generates one traceable test per acceptance criterion, so the
    acceptance_criteria list is REQUIRED and must be non-empty — a ticket with no
    criteria has nothing to verify.
    """

    key: str = Field(..., min_length=1, max_length=64)
    summary: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=20000)
    acceptance_criteria: list[str] = Field(..., min_length=1, max_length=200)
    definition_of_done: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("acceptance_criteria", "definition_of_done")
    @classmethod
    def _bound_item_length(cls, v: list[str]) -> list[str]:
        # Cap each entry so an adversarial ticket can't send an unbounded paid prompt.
        return [item[:2000] for item in v]


class GenerateFromTicketRequest(BaseModel):
    """Generate tests FROM a structured ticket (the tool's real purpose)."""

    ticket: JiraTicket
    framework: Literal["playwright", "cypress", "selenium"] = "playwright"
    output_file: Path | None = None
    use_cache: bool = True


class GenerateTestsResponse(BaseModel):
    id: int
    generated_code: str
    tokens_used: int
    validation_passed: bool
    output_file_path: str | None
    from_cache: bool = False


class TestLogEntry(BaseModel):
    test: str
    status: str
    duration: float = 0.0
    timestamp: datetime | None = None
    error_message: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        normalized = v.strip().upper()
        mapping = {
            "PASSED": "PASS",
            "SUCCESS": "PASS",
            "OK": "PASS",
            "FAILED": "FAIL",
            "FAILURE": "FAIL",
            "ERROR": "FAIL",
            "SKIPPED": "SKIP",
            "IGNORED": "SKIP",
        }
        return mapping.get(normalized, normalized)


class FlakyTestDetail(BaseModel):
    test_name: str
    fail_rate: float
    total_runs: int
    avg_duration_seconds: float
    ai_suggestion: str | None = None


class FlakyAnalysisRequest(BaseModel):
    logs: list[TestLogEntry]
    source_file: str | None = None


class FlakyAnalysisResponse(BaseModel):
    run_id: int
    flaky_tests: list[FlakyTestDetail]
    total_analyzed: int


class HealSelectorRequest(BaseModel):
    description: str = Field(..., min_length=2, max_length=256)
    old_selector: str = Field(..., min_length=1, max_length=512)
    html_snippet: str = Field(..., min_length=1, max_length=50000)
    force_heal: bool = False


class HealSelectorResponse(BaseModel):
    id: int
    new_selector: str
    validation_passed: bool
    from_cache: bool
    tokens_used: int


class DashboardSummary(BaseModel):
    generated_tests_count: int
    flaky_runs_count: int
    avg_flaky_rate: float
    healed_selectors_count: int
    last_activity_at: datetime | None
