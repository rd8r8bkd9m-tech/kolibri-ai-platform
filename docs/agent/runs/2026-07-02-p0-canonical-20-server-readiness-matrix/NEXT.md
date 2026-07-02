# Next

Task: `P0_CANONICAL_20_SERVER_READINESS_MATRIX_2026_07_02`

Next action: route new implementation work only to the `ready` pool after checking the shared-host 50 percent capacity governor; prefer `agent-08` or `agent-09` for immediate free implementation slots and `new` for review.

Follow-up repair tasks:

1. `primary` heartbeat and identity repair: normalize `primary` vs `primary-candidate`, restore heartbeat freshness <=30s, then run read-only GitHub/Codex/MIMO smoke.
2. `qjns` credential readiness repair: verify node-local GitHub clone/fetch, Codex/MIMO auth, and disposable-branch push only if explicitly authorized.
3. Offline-route restore: repair or retire `highload`, `paris`, `reserve242`, and `server-kfrm` Agent Host routes.
4. Metadata TTL cleanup: remove or quarantine stale metadata cards for old `agent-*` and server identities after confirming scheduler compatibility.
5. Home gateway canonicalization: choose `home` or `home-live` as the owner-facing route and prevent duplicate scheduling.
