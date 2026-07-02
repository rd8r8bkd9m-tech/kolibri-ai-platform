# PLAN

Task: `P0_PR137_HTTP_WORKER_THREAD_GROWTH_REPAIR_2026_07_02`.

Goal: continue from PR #137 head `93df313c8d4e70ab1e051ba64854a868b8ae9338`, preserve empty-poll `200/no_task`, and repair runtime canary `thread_growth` where stage 100 reached `122` threads against the `<=90` gate.

Plan:
1. Read PR #137 runtime failure evidence and canary thresholds.
2. Keep scope limited to Control Plane HTTP admission and focused capacity tests.
3. Clamp unsafe worker configuration so stale runtime env values cannot exceed the canary thread budget.
4. Preserve backlog/empty-poll behavior without adding a 503 worker gate.
5. Verify with focused pytest, runtime-only adjacent tests, `py_compile`, `git diff --check`, and a subprocess stage probe.
