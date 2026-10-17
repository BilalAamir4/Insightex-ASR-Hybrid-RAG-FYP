# insightex.llm

**Purpose:** Client for the Ollama LLM. `ollama_client.chat_json(messages, schema, num_ctx, ...)` posts to `/api/chat` with `think: false`, a JSON Schema `format` (from a pydantic model) and validates the reply; `num_ctx` is required. `chat_raw(messages, format_schema, num_ctx, ...)` is the same call with a JSON Schema dict as `format`, returning the unparsed content (M7 extraction validates it itself); `chat_json` is built on it. `model_digest(model)` reads the tag's digest from `/api/tags`. `unload()` sends `keep_alive: 0` and polls `/api/ps`.

**Model used:** Ollama qwen3.5:latest. The exact name is checked against `/api/tags` before the first call.

**Feature numbers:** not assigned

**Status:** M0 client only. Measurements: `docs/measurements/2026-10-07_ollama_contract.md`. Self-test: `python -m insightex.llm.ollama_client --selftest | --unload`.
