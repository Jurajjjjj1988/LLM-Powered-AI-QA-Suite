# Claude / Anthropic SDK usage

- **Model IDs (current):** default `claude-opus-4-8`; use `claude-sonnet-4-6` for cheap/bulk calls. NEVER hardcode a stale `claude-3-*` / `claude-opus-4-6` string — centralise the model constant in `common/`.
- **Structured output via Pydantic** — use the SDK's parse/tool path so the response is a validated model. Never `json.loads` a hand-built prompt's text and hope.
- **Stream** long or high-`max_tokens` output; use adaptive thinking for hard reasoning.
- **Resilience:** wrap every API call with `tenacity` retry on transient errors; check `stop_reason` (incl. `refusal`) before reading content.
- **Cost:** cache the stable context (system prompt, schemas) via prompt caching; cache results by input hash where the suite already does (generator/healer).
- All of this belongs in the shared `common/claude_client.py` — tools call the wrapper, not `anthropic` directly.
