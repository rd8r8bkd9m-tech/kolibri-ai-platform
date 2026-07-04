# PLAN

Task: `P0_KOLIBRI_CONTROL_GATEWAY_ACTION_MCP_AND_FACTORY_REPAIR_NOW_20260704`

1. Repair `ops/chatgpt_action_gateway.py` as a thin GPT Action adapter over Control Plane.
2. Replace single Control Plane URL with bounded fallback list.
3. Add structured responses with `control_plane_used`, fallback evidence, blocker and next action.
4. Produce GPT Builder OpenAPI and MCP tools spec.
5. Prove Start Factory path with one safe canary task or record exact blocker.
6. Update PR #166 without merging.
