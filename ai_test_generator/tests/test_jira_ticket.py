"""Tests for the ticket parser (ai_test_generator.jira_ticket.parse_ticket).

Covers the two real sources it must handle:
- a Jira-style export (key PROJ-123, '## Acceptance Criteria' + '## Definition of Done')
- a GitHub issue (`gh issue view` output) that uses a task-list checklist, often with
  no explicit 'Acceptance Criteria' heading.
And the guard: a ticket with no criteria must raise, not silently produce nothing.
"""

from __future__ import annotations

import pytest

from ai_test_generator.jira_ticket import parse_ticket
from common.exceptions import TicketParseError

JIRA_TICKET = """\
# PROJ-123 Reset password

## Description
A user who forgot their password can request a reset link by email.

## Acceptance Criteria
- Requesting a reset with a valid email sends a reset link
- An unknown email shows a generic message (no user enumeration)
- The reset link expires after 60 minutes

## Definition of Done
- Works on a mobile viewport
- Error states show a visible message
"""

GITHUB_ISSUE = """\
# Add-to-cart from product page  #42

The cart should update immediately when a user adds an item.

- [ ] Adding an in-stock item increases the cart badge count
- [x] Adding an out-of-stock item is blocked with a message
- [ ] The cart persists after a page reload
"""


class TestParseJiraTicket:
    def test_should_extract_the_jira_key(self) -> None:
        assert parse_ticket(JIRA_TICKET).key == "PROJ-123"

    def test_should_extract_the_summary_without_the_key(self) -> None:
        assert parse_ticket(JIRA_TICKET).summary == "Reset password"

    def test_should_extract_all_acceptance_criteria_in_order(self) -> None:
        ticket = parse_ticket(JIRA_TICKET)
        assert len(ticket.acceptance_criteria) == 3
        assert ticket.acceptance_criteria[0].startswith("Requesting a reset")
        assert "expires after 60 minutes" in ticket.acceptance_criteria[2]

    def test_should_extract_definition_of_done(self) -> None:
        ticket = parse_ticket(JIRA_TICKET)
        assert len(ticket.definition_of_done) == 2
        assert "mobile viewport" in ticket.definition_of_done[0]

    def test_should_not_leak_criteria_into_the_description(self) -> None:
        ticket = parse_ticket(JIRA_TICKET)
        assert "reset link" in ticket.description
        assert "expires after 60 minutes" not in ticket.description


class TestParseGithubIssue:
    def test_should_treat_a_heading_less_checklist_as_the_criteria(self) -> None:
        ticket = parse_ticket(GITHUB_ISSUE)
        assert len(ticket.acceptance_criteria) == 3

    def test_should_strip_the_checkbox_marker(self) -> None:
        ticket = parse_ticket(GITHUB_ISSUE)
        assert (
            ticket.acceptance_criteria[0]
            == "Adding an in-stock item increases the cart badge count"
        )
        # a ticked [x] box is still a criterion, marker removed
        assert ticket.acceptance_criteria[1].startswith("Adding an out-of-stock item")

    def test_should_derive_a_github_key_when_no_jira_key(self) -> None:
        assert parse_ticket(GITHUB_ISSUE).key == "GH-42"


class TestLenientFormats:
    def test_should_accept_a_colon_heading_and_numbered_list(self) -> None:
        text = (
            "TASK-7 Search returns results\n"
            "Acceptance Criteria:\n"
            "1. A valid query returns at least one result\n"
            "2. An empty query keeps the user on the page\n"
        )
        ticket = parse_ticket(text)
        assert ticket.key == "TASK-7"
        assert len(ticket.acceptance_criteria) == 2

    def test_should_accept_a_bold_heading(self) -> None:
        text = "# ABC-9 Thing\n**Acceptance Criteria**\n- does the thing\n"
        assert parse_ticket(text).acceptance_criteria == ["does the thing"]


class TestGuards:
    def test_should_raise_when_no_criteria_present(self) -> None:
        text = "# PROJ-1 A title\n\nJust a prose description with no criteria at all.\n"
        with pytest.raises(TicketParseError):
            parse_ticket(text)

    def test_should_raise_on_empty_input(self) -> None:
        with pytest.raises(TicketParseError):
            parse_ticket("   \n  ")


class TestReviewRegressions:
    """Regressions for defects the adversarial review confirmed in the parser."""

    def test_should_not_treat_a_colon_terminated_bullet_as_a_heading(self) -> None:
        # A criterion ending in ':' must NOT flip the section off and drop later bullets.
        text = (
            "# PROJ-9 Colonic\n\n## Acceptance Criteria\n"
            "- The user sees the following on login:\n"
            "- a welcome banner\n"
            "- the last login time\n"
        )
        assert len(parse_ticket(text).acceptance_criteria) == 3

    def test_should_not_mistake_a_standards_token_for_a_key(self) -> None:
        text = "# Fix ISO-8601 date parsing\n\n## Acceptance Criteria\n- dates parse correctly\n"
        ticket = parse_ticket(text)
        assert ticket.key != "ISO-8601"
        # the standards token is NOT gouged out of the summary
        assert "ISO-8601" in ticket.summary

    def test_should_ignore_checkboxes_inside_a_fenced_code_block(self) -> None:
        text = (
            "# PROJ-3 Docs\n\n## Acceptance Criteria\n"
            "- the real criterion\n\n"
            "```md\n- [ ] this is a documentation example, not a criterion\n```\n"
        )
        acs = parse_ticket(text).acceptance_criteria
        assert acs == ["the real criterion"]

    def test_should_join_a_wrapped_criterion(self) -> None:
        text = (
            "# PROJ-4 Wrap\n\n## Acceptance Criteria\n"
            "- The system must reject a request when the token is expired\n"
            "  and show a clear re-authentication message\n"
        )
        acs = parse_ticket(text).acceptance_criteria
        assert len(acs) == 1
        assert "re-authentication message" in acs[0]

    def test_should_fold_indented_sub_bullets_into_the_parent(self) -> None:
        text = (
            "# PROJ-5 Nested\n\n## Acceptance Criteria\n"
            "- Checkout supports:\n"
            "    - credit card\n"
            "    - paypal\n"
        )
        assert len(parse_ticket(text).acceptance_criteria) == 1

    def test_should_recognise_a_numbered_section_heading(self) -> None:
        text = "# PROJ-6 Numbered\n\n### 1. Acceptance Criteria\n- it works\n"
        assert parse_ticket(text).acceptance_criteria == ["it works"]

    def test_should_not_crash_on_a_very_long_uppercase_title(self) -> None:
        text = "# " + ("X" * 300) + "\n\n## Acceptance Criteria\n- it works\n"
        ticket = parse_ticket(text)  # must not raise a raw Pydantic ValidationError
        assert len(ticket.key) <= 64

    def test_should_not_raise_on_a_prose_only_acceptance_section(self) -> None:
        text = (
            "# PROJ-7 Gherkin\n\n## Acceptance Criteria\n"
            "Given a logged-in user\nWhen they log out\nThen they see the login page\n"
        )
        assert len(parse_ticket(text).acceptance_criteria) >= 1
