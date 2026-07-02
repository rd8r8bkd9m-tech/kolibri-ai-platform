# Next

- Open a PR from branch `agent/P0_PRODUCT_AGENT_TASK_ARTIFACTS_API_IMPLEMENT_2026_07_02/generic` if GitHub credentials are available in the owner environment.
- Run the full backend suite in an environment with `httpx` and `pydantic` installed.
- After merge/deploy, canary the live control plane with non-secret sample calls to `/v1/agents/tasks`, `/v1/agents/status/{task_id}`, `/v1/agents/artifacts/{task_id}`, and `/v1/agents/cancel/{task_id}`.
