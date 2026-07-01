# Post-Merge Canary Plan

Draft canary requirements for remote release steward validation:

| PR | Canary |
| --- | --- |
| #88 | Confirm dispatcher docs render and queue files remain parseable. |
| #92 | Confirm fleet inventory docs are present in `main` and referenced by dispatcher status. |
| #96 | Deploy/restart Agent Host on a canary node, run read-only/no-push permission-pack task, confirm forbidden operations are blocked before work starts. |
| #97 | Deploy/restart Control Plane canary, confirm stale node cards do not inflate online capacity and freshness fields are visible. |
| #85 | Run Fabric API contract tests and a read-only task submission/status/artifact roundtrip through `/v1` surfaces. |
| #91 | Run MIMO output/auth parser canary on a bounded remote task and confirm provider auth failures are classified without leaking secrets. |
| #89 | Run Telegram receiver single-owner canary before any live cutover; no duplicate polling/webhook receiver. |
| #83 | Run full Agent Host runner contract canary if it remains a merge candidate after #96 comparison. |

No canary is executed by this preparation task.
