# P0 Product Agent Task Artifacts API Implement Plan

Task: `P0_PRODUCT_AGENT_TASK_ARTIFACTS_API_IMPLEMENT_2026_07_02`

Plan:
- Preserve legacy `/v1/tasks` storage and runner contracts.
- Repair the product-facing `/v1/agents/tasks`, `/v1/agents/status/{task_id}`, `/v1/agents/artifacts/{task_id}`, and `/v1/agents/cancel/{task_id}` facade.
- Add focused tests for UI/Telegram status, artifacts, and cancellation behavior.
- Run focused and dependency-free compatibility verification.
