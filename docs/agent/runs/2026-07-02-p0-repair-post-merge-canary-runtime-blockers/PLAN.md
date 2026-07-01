# Plan

Task id: `P0_REPAIR_POST_MERGE_CANARY_RUNTIME_BLOCKERS_2026_07_02`

Node: `kolibri`

Russian agent display name: `Сергей - Runtime Blocker Repair Steward`

Plan:

1. Import the source canary artifacts into this branch and repair the missing
   `NEXT_REMOTE_TASKS.md` artifact.
2. Verify this is server/control-node execution, not local Mac execution.
3. Reprobe B1-B4 with read-only commands and redacted evidence.
4. Repair only safe artifact/env-contract issues; classify runtime/service/API
   blockers that need owner approval or deployment work.
5. Run focused verification without modifying product code, tests, CI, secrets,
   Telegram Bot API state, services, or `main`.

Guardrails:

- No product code, tests, CI files, Telegram tokens, secrets, or `main` are
  modified.
- No service restart is performed in this repair task.
- No Telegram Bot API method is called.
- Exact artifacts are written under `docs/agent/runs/**` only.

