"""
Prompt templates for ai-test-generator.

Design principle: system prompt is STATIC and defines role/constraints only.
User-supplied content is ALWAYS placed in the user message to prevent prompt injection.
"""

SYSTEM_PROMPT = """\
You are an expert QA engineer specialising in writing automated test suites.
You produce clean, production-ready test code with no explanations, no markdown
fences, and no surrounding text — ONLY raw source code.

Rules you MUST follow:
1. Return ONLY valid source code for the requested framework.
2. Do NOT include triple-backtick fences or language tags.
3. Do NOT add any commentary before or after the code.
4. Every test file MUST start with the appropriate import statements.
5. Include at minimum: happy-path tests, one negative/edge-case test, and
   teardown/cleanup where applicable.
6. Use descriptive test names that read as plain English sentences.
"""


def build_playwright_user_message(requirement: str) -> str:
    """
    Build the user message for a Playwright TypeScript test.
    The requirement text is injected here (user turn), never in the system prompt.
    """
    return (
        "Generate Playwright TypeScript tests for the following requirement.\n\n"
        "Requirements:\n"
        f"{requirement}\n\n"
        "Constraints:\n"
        "- Use `import { test, expect } from '@playwright/test';` at the top.\n"
        "- Wrap related tests inside a `test.describe` block.\n"
        "- Use `test.beforeEach` / `test.afterEach` where state setup is needed.\n"
        "- Use `await expect(locator).toBeVisible()` style assertions.\n"
        "- Each `test(` block must have a unique, descriptive name.\n"
        "- Return ONLY the TypeScript source code. No markdown, no explanations."
    )


def build_cypress_user_message(requirement: str) -> str:
    """
    Build the user message for a Cypress TypeScript test.
    """
    return (
        "Generate Cypress TypeScript tests for the following requirement.\n\n"
        "Requirements:\n"
        f"{requirement}\n\n"
        "Constraints:\n"
        "- Use `import { describe, it, beforeEach } from 'mocha';` style is fine,\n"
        "  but rely on Cypress globals (cy, describe, it, expect) as typical.\n"
        "- Wrap tests in a `describe()` block.\n"
        "- Use `cy.get()`, `cy.contains()`, `.should()` style assertions.\n"
        "- Include `beforeEach` with `cy.visit()` where appropriate.\n"
        "- Return ONLY the TypeScript source code. No markdown, no explanations."
    )


def build_selenium_user_message(requirement: str) -> str:
    """
    Build the user message for a Selenium Python test.
    """
    return (
        "Generate Selenium Python tests (using pytest + selenium) for the following "
        "requirement.\n\n"
        "Requirements:\n"
        f"{requirement}\n\n"
        "Constraints:\n"
        "- Use `import pytest` and `from selenium import webdriver` at the top.\n"
        "- Use pytest fixtures for driver setup/teardown.\n"
        "- Include at least one parametrized test with `@pytest.mark.parametrize`.\n"
        "- Use explicit waits (`WebDriverWait`) rather than `time.sleep()`.\n"
        "- Return ONLY the Python source code. No markdown, no explanations."
    )


# Dispatch table so generate_tests.py can call build_user_message(framework, req)
_FRAMEWORK_BUILDERS = {
    "playwright": build_playwright_user_message,
    "cypress": build_cypress_user_message,
    "selenium": build_selenium_user_message,
}


def build_user_message(framework: str, requirement: str) -> str:
    """
    Return the correct user-turn message for the given framework.
    Raises ValueError for unknown frameworks.
    """
    builder = _FRAMEWORK_BUILDERS.get(framework.lower())
    if builder is None:
        supported = ", ".join(_FRAMEWORK_BUILDERS)
        raise ValueError(
            f"Unknown framework {framework!r}. Supported: {supported}"
        )
    return builder(requirement)
