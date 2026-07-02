# Plan

Task id: `P0_AUTOPILOT_EXTRA_21_RESERVE242_READINESS_2026_07_02`

1. Confirm this task is running on the assigned server-side mesh worker.
2. Probe Control Plane and fallback Fabric API routes for `reserve242`.
3. Extract sanitized node cards for `reserve242` and `mesh-reserve242`.
4. Classify readiness, capacity, blockers, fallback viability and exact repair task.
5. Produce owner-facing Russian summary and artifact-backed result.

Safety constraints:

- No product code changes.
- No secrets printed.
- No destructive git commands.
- No push to `main`.
- Read-only API probes only.
