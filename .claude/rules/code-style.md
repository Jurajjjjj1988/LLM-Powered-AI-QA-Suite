# Python code style (the quality bar)

- **Type everything.** Every public function/method has parameter AND return-type hints. `ruff check .` stays clean. No `Any`/bare `dict` where a Pydantic model or `TypedDict` belongs.
- **Pydantic v2 for all structured data** — LLM output, config (`pydantic-settings`), DB DTOs. Never hand-parse fragile JSON from the model.
- **No bare `except:`** — catch specific exceptions. Wrap transient external calls (`anthropic`, DB, network) with `tenacity` retry.
- **Docstrings** on every public function, class, and module (one-line summary minimum).
- **One shared pattern, not per-tool sprawl.** The Claude client, config, DB access, logging, and CLI scaffolding live in `common/` and every tool imports them — never re-implement per tool.
- **No flat-module collisions.** Tools must be importable without `import prompts` resolving to another tool's `prompts.py`. Each tool is a proper namespaced package; tests import via the tool's namespace, never a bare shared name.
- `ruff format .` is the formatter; line length + rules come from `pyproject.toml` — don't fight it.
