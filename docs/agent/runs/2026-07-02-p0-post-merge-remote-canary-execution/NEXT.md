# Next

Exact next task:

`P0_REPAIR_POST_MERGE_CANARY_RUNTIME_BLOCKERS_2026_07_02`

Objective:

On a server/control node, repair or route around the runtime blockers found by `P0_POST_MERGE_REMOTE_CANARY_EXECUTION_2026_07_02` without changing product code or secrets: restore/read-only classify Telegram gateway runtime, identify the authoritative live Fabric API listener or fix `/v1` route mounting, sync Python test dependencies needed for factory-status freshness tests, and perform a GitHub PR metadata recheck from an authenticated node. Then rerun the post-merge remote canary against main `c97a0f50e14e3c2c20babfd13fbeb045400f66f2` or its fetched successor.

Required acceptance:

- No Telegram API mutation unless explicitly authorized.
- No PR merge/approval/ready/close action.
- No push to `main`.
- Runtime blockers are either cleared with exact evidence or left blocked with exact evidence.
- Canary is rerun only after current main SHA is freshly verified.

