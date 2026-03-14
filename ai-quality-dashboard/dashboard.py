# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Fixed

- **CheckoutPage**: Selectize city autocomplete — replaced `fill()` with `type({ delay: 150 })` on `.selectize-control input[type="text"]` to correctly trigger autocomplete suggestions
- **CheckoutPage**: Selectize street autocomplete — use `.selectize-control nth(1)` selector + `waitForSelector('.selectize-dropdown-content .option', { state: 'attached' })` to handle `display:none` visibility issue
- **CheckoutPage**: Replaced `clear()` + `fill()` with `click({ clickCount: 3 })` + `fill()` to prevent stray `\` character in city field
- **CartPage**: `addServices()` — added `clickServiceButton()` helper with `toBeEnabled()` assert and `waitForTimeout(1500)` between each service button click to handle `aria-disabled="true"` after Livewire re-render
- **CartPage**: Use fresh locator via `btn()` arrow function to avoid stale element references after DOM re-render
- **PhonesPage**: `selectTariff()` — replaced `waitForResponse('**/telefony**')` with `waitForLoadState('networkidle') + waitForTimeout(2000)` as Livewire uses its own endpoint
- **PhonesPage**: `sortBy()` — same fix as `selectTariff()`, target `#order` select element directly
- **PhonesPage**: `clickPhone()` — added `waitForTimeout(2000)` before locator, `waitFor({ state: 'visible' })` and `scrollIntoViewIfNeeded()` before click
- **HomePage**: `acceptCookies()` — added `Promise.race()` with `try/catch` fallback for multiple cookie banner button text variants

### Added

- **playwright.config.ts** — global `timeout: 120000`, `actionTimeout: 15000`, `navigationTimeout: 30000`

---

## [1.0.0] - 2026-03-11

### Added

- Initial E2E test for Orange SK iPhone purchase flow (`test.spec.ts`)
- Page Object Model structure: `HomePage`, `PhonesPage`, `ProductPage`, `CartPage`, `CheckoutPage`
- Full nákupný flow: homepage → telefóny → produkt → košík → checkout → osobné údaje
- `PersonalDetails` interface in `CheckoutPage`
- Cookie acceptance in `beforeEach` hook
- Test steps via `test.step()` with Slovak descriptions
