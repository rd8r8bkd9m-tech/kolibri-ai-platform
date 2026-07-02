# Actions

Changed implementation:

- Added local model endpoint inventory to `ops/factory_control.py`.
- Added default candidates for Ollama, vLLM, LiteLLM, and a generic OpenAI-compatible endpoint.
- Added `KOLIBRI_LOCAL_MODEL_ENDPOINTS` support for extra comma- or semicolon-separated OpenAI-compatible model bases.
- Added `/v1/models` response fields:
  - `local_model_route_inventory`
  - `first_working_route`
  - `repair_task`
- Kept `mimo-auto` in the model catalog as the safe fallback stub.
- Added tests for:
  - first working OpenAI-compatible local route discovery
  - exact blocker when no route is reachable

Live execution performed:

- Probed local model endpoint candidates.
- Verified the live Fabric listener at `http://10.99.0.10:9101/v1/models` currently returns only `mimo-auto`.
- Confirmed Docker is available and no host `ollama` binary is installed.

No secrets were printed or read from environment dumps.
