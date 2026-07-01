# Repair and Deployment Backlog

Task: `P0_FLEET_ROLE_CAPABILITY_INVENTORY_2026_07_01`
Generated: `2026-07-01T13:14:29.380888+00:00`

1. `qjns` GitHub/MIMO credential repair: fresh and online, but advertises no `runner:*`; treat GitHub push/review and MIMO execution as unverified. Run a future explicit repair task that checks runner binary, auth status, git remote auth, and safe push to a disposable branch without disclosing credentials.
2. Main runner auth verification: `main` is fresh and advertises `runner:codex` and `runner:mimo`, but has low available memory. Verify GitHub/MIMO/Codex auth with a read-only or disposable-branch smoke before assigning push/review work.
3. Stale mesh card cleanup: stale mesh-only cards (`mesh-agent-04..09`, `mesh-highload`, `mesh-home`, `mesh-main`, `mesh-new`, `mesh-paris`, `mesh-primary`, `mesh-qjns`, `mesh-reserve242`, `mesh-server-kfrm`, `mesh-uiap`) should be retired or refreshed by the mesh bridge; do not target them for implementation.
4. Stale metadata card retention: metadata-only cards (`9fts`, `agent-01..09`, `highload`, `paris`, `reserve242`, `server-kfrm`, `smoke-primary`) duplicate or predate live agent cards. Add retention policy or TTL cleanup after confirming no scheduler depends on them.
5. `qjns` / `uiap` retention: queue contains targeted historical work for `uiap` and related node identities. Add an owner-approved queue retention/cancel policy for stale targeted tasks before general scheduling resumes.
6. `home` / `home-live` freshness repair: both owner-facing gateway/orchestrator cards are stale despite strong capabilities. Restore heartbeat freshness before using them for owner-facing routing or standby Control Plane work.
7. Queue pressure cleanup: Control Plane reports 236 queued tasks and returned task scan is truncated. Schedule a read-only queue audit, then cancel or archive obsolete cluster/MIMO probe tasks with owner approval.
8. Capability taxonomy repair: unify `implementation` vs `generic_implementation`, `review`, `qa`, `runner:*`, and mesh-shadow capabilities so scheduler target pools are explicit rather than inferred from stale card names.

No repair was performed by this inventory task.
