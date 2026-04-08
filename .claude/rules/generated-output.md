# Generated test OUTPUT quality (ai-test-generator)

When `ai-test-generator` emits **Playwright** code, the output MUST follow the `layered-playwright-suite` skill (`~/.claude/skills/layered-playwright-suite/`), not a flat bare spec:

- The spec imports `test`/`expect` from `@fixtures/base.fixture`, NEVER `@playwright/test`.
- Locators live in a **page object** (`readonly` fields with `.describe('[LABEL] …')`), never inline in the spec; page classes have NO own constructor (BasePage wires `page`).
- Web-first assertions only — no hard waits, no `.nth()`, no CSS-class primary locator.
- Role-split helper tree (page-object / fixtures / api / actions / utilities / test-data).

Wire these conventions into the generator's Playwright prompt/templates + validate the output against them before persisting. Cypress/Selenium targets keep their own idioms but the same "clean, senior-written" bar.
