# Next

Recommended next exact task:

`P0_LOCAL_MODEL_NODE_DISCOVERY_AND_GATEWAY_CONTRACT_2026_07_02`

Target:

- primary: `mesh-agent-01`
- fallback: `mesh-agent-02`
- avoid until repaired: `qjns`, stale `home`/`home-live`, stale metadata cards

Objective:

Read-only server discovery plus docs-only contract. Inventory whether Ollama,
vLLM, LiteLLM, MIMO and Kimi routes exist on model-capable nodes. Do not install
models, download weights, rotate credentials, restart services, or print env
values. Report only configured/not configured status for secret-bearing values.

Required output artifacts:

- `HARDWARE_INVENTORY.md`
- `MODEL_SERVICE_INVENTORY.md`
- `MODEL_GATEWAY_CONTRACT.md`
- `LOCAL_MODEL_REGISTRY_DRAFT.md`
- `BLOCKERS.md`
- `RESULT.md`
- `NEXT.md`

Acceptance:

- exact node and agent identity included;
- Ollama/vLLM/LiteLLM/MIMO/Kimi status classified;
- `/v1/models`, `/v1/responses` and `/v1/chat/completions` route contracts
  drafted;
- no secrets printed;
- no product code changed unless a separate implementation task is approved;
- Russian owner-facing summary included.

