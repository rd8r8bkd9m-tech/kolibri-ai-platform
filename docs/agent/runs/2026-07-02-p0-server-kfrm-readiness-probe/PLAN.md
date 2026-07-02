# Plan

Task id: `P0_AUTOPILOT_EXTRA_34_KFRM_READINESS_2026_07_02`

Goal: probe `server-kfrm` readiness, API route, service status, disk, GitHub
auth, and exact repair task from a server-side mesh worker.

Constraints:

- Read-only operational probe.
- No product code changes.
- No destructive git commands, no force push, no push to `main`.
- Do not print secrets or environment files.
- Produce owner-facing Russian summary and artifact-backed result.

Steps:

1. Confirm execution context and active worker identity.
2. Probe Control Plane route for `server-kfrm`.
3. Probe service status for Factory/Agent Host services.
4. Probe local disk availability for the executing worker.
5. Probe GitHub auth without printing credential material.
6. Record blockers and the exact next repair task.
