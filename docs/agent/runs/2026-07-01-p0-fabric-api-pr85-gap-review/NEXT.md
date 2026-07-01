# NEXT

Task: `2026-07-01-p0-fabric-api-pr85-gap-review`
Reviewer: `Алексей — Fabric API Reviewer`
Node: `primary-candidate:agent-host-primary`

Next exact task: `P0_PR85_PROMPT3_FABRIC_API_SURFACE_REPAIR_2026_07_01`

Goal: repair PR #85 in-place so it satisfies Prompt #3 before owner merge review.

Required repair scope:

1. Implement `/v1/fleet/nodes`, `/v1/fleet/topology`, `/v1/fleet/route`, `/v1/fleet/capabilities` over existing node/fabric route data.
2. Implement `/v1/agents/tasks`, `/v1/agents/status/{task_id}`, `/v1/agents/artifacts/{task_id}`, `/v1/agents/cancel/{task_id}` as aliases over existing task control-plane endpoints.
3. Add deny-by-default safe stubs for `/v1/admin/exec`, `/v1/admin/service`, `/v1/admin/git`, `/v1/admin/bootstrap-node`, `/v1/admin/rotate-keys` with explicit auth/scope/audit blocked envelopes.
4. Add OpenAI-compatible contracts or safe stubs for `/v1/models`, `/v1/responses`, `/v1/chat/completions`.
5. Add canonical request/response envelope helpers and validation tests.
6. Expand fallback reason taxonomy tests.
7. Fix documentation EOF whitespace so `git diff --check` passes.

Do not merge PR #85 until this task is complete and CI is green.
