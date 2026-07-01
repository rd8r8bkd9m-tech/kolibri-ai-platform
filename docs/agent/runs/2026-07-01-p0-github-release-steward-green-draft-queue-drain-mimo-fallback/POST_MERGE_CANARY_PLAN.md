# Post-Merge Canary Plan

No canary was executed by this artifact-only fallback task.

| PR | Required canary after owner-approved merge |
| --- | --- |
| #88 | Confirm dispatcher ledger docs render, queue links resolve, and dispatcher files remain parseable. |
| #92 | Confirm fleet inventory docs are present on `main`, referenced from dispatcher/status docs, and do not claim stale node capacity as live capacity. |
| #96 | Deploy/restart Agent Host on one canary node. Submit a no-push/read-only task and prove write-capable permission packs are stripped or blocked before execution. Confirm no push command runs. |
| #97 | Deploy/restart Control Plane canary. Confirm stale heartbeat nodes are excluded from live capacity and freshness timestamps/status fields are visible. |
| #85 | Run focused Fabric API contract tests. Then run a read-only `/v1` task submission, status lookup, and artifact retrieval roundtrip. |
| #91 | Submit a bounded MIMO task with simulated provider auth/output edge cases. Confirm auth failures are classified without secret leakage and artifacts are written exactly once. |
| #89 | Before live cutover, prove exactly one Telegram receiver is active. Confirm webhook/poller state is intentional, owner-only commands still gate privileged actions, and no duplicate message handling occurs. |
| #83 | If still merge-relevant after #96, run the full Agent Host runner contract canary: review clone, no-push artifact task, missing-artifact failure, and auth-failure result emission. |

Canary sequencing:

1. Docs presence checks for #88/#92.
2. Runtime safety checks for #96/#97.
3. API roundtrip for #85.
4. MIMO classification canary for #91.
5. Telegram receiver/cutover canary for #89.
6. Agent Host runner overlap canary for #83 only if not superseded.
