# Plan

Task: `P0_POST_MERGE_REMOTE_CANARY_EXECUTION_2026_07_02`

Agent display name: `Сергей - Remote Canary Steward`

Execution node: `kolibri`

Scope:

- Run from the checked-out server/control-node worktree only.
- Verify current `origin/main` before classifying the canary.
- Cover Agent Host, MIMO, Control Plane freshness, Fabric API, Telegram runtime, and GitHub PR queue.
- Produce exactly nine run artifacts under this directory.
- Do not modify product code, tests, CI, services, Telegram settings, secrets, or `main`.
- Do not merge, approve, close, mark ready, force-push, or push to `main`.

Canary method:

1. Refresh and verify `origin/main`.
2. Record server identity and service state without printing secrets.
3. Run focused local test-backed canaries for Agent Host, MIMO, Fabric API contracts, Telegram runtime contracts, and queue contracts.
4. Probe live Control Plane/Fabric health endpoints read-only.
5. Probe GitHub queue visibility read-only through git refs because `gh` is unavailable on this node.
6. Classify any runtime blockers with exact command evidence.

