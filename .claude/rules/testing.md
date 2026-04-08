# Testing discipline

- **pytest**, behaviour-first: every test answers *"would this fail if the behaviour broke?"* Given input → asserted output. No trivial "it imports" tests.
- **Mock the Claude API** (`pytest-mock` / a fake `ClaudeClient`) — the suite MUST run offline + free. A test that hits the real Anthropic API is wrong.
- **Every tool has real tests**; every public function in `common/` is covered. The 3 thin/untested tools (debug-accelerator, mock-architect, dashboard) are the priority gap.
- Tests live under `<tool>/tests/`; pytest runs with `--import-mode=importlib`. No cross-tool bare imports in tests (they resolve to the wrong tool — see code-style).
- `pytest -q` (mocked) must be green before any commit; `pytest --cov` tracks the floor.
