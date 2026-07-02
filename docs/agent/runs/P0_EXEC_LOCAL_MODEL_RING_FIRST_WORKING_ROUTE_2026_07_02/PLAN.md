# Plan

Task: `P0_EXEC_LOCAL_MODEL_RING_FIRST_WORKING_ROUTE_2026_07_02`

1. Inspect the Fabric model listing implementation and existing route contracts.
2. Probe local model runtime candidates without printing secrets:
   - Ollama: `http://127.0.0.1:11434/api/tags`
   - vLLM/OpenAI-compatible: `http://127.0.0.1:8000/v1/models`
   - LiteLLM: `http://127.0.0.1:4000/v1/models`
   - Generic OpenAI-compatible: `http://127.0.0.1:8080/v1/models`
3. Add read-only local model route discovery to `/v1/models`.
4. Preserve the existing safe `mimo-auto` stub when no local runtime is reachable.
5. Return the first working local model route in the Fabric model listing when available.
6. Return an exact deploy blocker when no local model runtime is reachable.
7. Verify with focused unit tests, syntax checks, and a live local discovery invocation.
