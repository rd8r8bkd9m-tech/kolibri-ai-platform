# Release Train Order

No merge to `main` was performed.

Recommended next order:

1. #113 `P0: repair factory-control runtime import path`
   - Reason: restores/guards factory-control runtime import path and service unit behavior before relying on later canaries.
2. #109 `P0: repair factory status proxy 504 canary`
   - Reason: owner/fleet visibility should be fast and reliable before release acceleration continues.
3. #112 `P0: repair runner timebox and max-inflight contract`
   - Reason: enforces execution guardrails before increasing queue pressure or broad repair fanout.
4. #105 `P0: make Fabric route selection freshness-aware`
   - Reason: route freshness is core for safe node selection; repair branch is currently empty, so review the existing #105 diff and CI/check state directly.
5. #110 `P0: repair primary node heartbeat read-only path`
   - Reason: overlaps `ops/factory_control.py` and fleet freshness; should be compared against #105 before merge.
6. #108 `P0: repair fleet online freshness accelerator`
   - Reason: fleet online accelerator also changes `ops/factory_control.py`; merge only after the primary freshness path is stable or explicitly reconcile conflicts.
7. #106 `P0: repair runner contract steward fallback`
   - Reason: runner contract follow-up touches `ops/agent_host.py`; compare with #112 first to avoid split-brain runner semantics.
8. #107 `P0: add release queue accelerator`
   - Reason: queue acceleration should wait until runtime import, status visibility, timebox, and freshness repairs are stable.
9. #111 `P0: add queue lease debt audit and requeue policy`
   - Reason: queue mutation/requeue policy should follow the core runtime and acceleration review.
10. #90 `Repair Telegram Mini App owner auth verifier contract`
   - Reason: keep open as draft until the dependency-satisfied verifier path and system-Python/import collision story is repaired or explicitly accepted.

Operational follow-ups:

- Run a check-run-capable CI inspection for #105 and #106-#113; this server lacks `gh`, and connector combined statuses returned no contexts.
- Dispatch real repair work for the empty PR #105 and PR #90 repair branches, or close/archive those empty branches if they were placeholders.
- Keep Telegram live receiver cutover separate from PR #90; do not enable competing receivers as part of this release train.
