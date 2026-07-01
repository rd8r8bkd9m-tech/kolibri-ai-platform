# Plan

Task: `P0_REPAIR_QJNS_GITHUB_AND_MIMO_AUTH_2026_07_01`

Agent display name: Николай - инженер восстановления qjns

Target node: `qjns`

Constraints:
- Do not run on Mac; execution host is Linux `kolibri`.
- Do not print secrets or inspect full secret-bearing files.
- Do not change product code.
- Use existing Control Plane, qjns Agent Host, and approved credentials only.

Steps:
1. Confirm command/control execution host is not macOS.
2. Read Control Plane node state for `qjns`.
3. Attempt approved remote access routes without password prompts.
4. Run a bounded qjns MIMO probe through Control Plane.
5. Run a bounded qjns GitHub clone/auth probe through Control Plane.
6. Record final qjns node card with `disk`, `health`, and `active_task`.
7. Classify unresolved blockers precisely and define the next action.
