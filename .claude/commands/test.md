Run the full test suite (Claude API mocked — offline + free):

```bash
.venv/bin/pytest -q --import-mode=importlib
```
For one tool: `.venv/bin/pytest <tool>/tests -q`. Coverage: add `--cov`. Must be green before commit.
