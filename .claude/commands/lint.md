Run the lint + format gate and report what's dirty:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```
Fix with `.venv/bin/ruff check --fix .` + `.venv/bin/ruff format .`, then re-run. Must be clean before commit.
