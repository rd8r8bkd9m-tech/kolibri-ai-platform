# Server cluster readiness

## Summary

- target nodes: 20.
- Control Plane cards seen: 20.
- direct SSH reachable from Mac: 2.
- direct SSH timeout from Mac: 18.
- full worker/resource cards: about 10 nodes.
- mesh-only/degraded cards: about 10 nodes.

## Node table

| Node | CP status | Role/caps summary | Resource note | Direct SSH from Mac | Risk |
|---|---|---|---|---|---|
| home | online fresh | coordinator, home, mesh, control standby, orchestrator, implementation | disk about 17.9 GB | timeout | jump route dependency |
| main | online fresh | orchestrator, implementation, review, codex/mimo runners | disk about 7.3 GB | reachable | dirty runtime repo, GitHub auth |
| uiap | online fresh | RAG, knowledge, security | disk 0.0 GB | timeout | P0 disk |
| qjns | online fresh | tools executor, QA, implementation | disk 0.0 GB | timeout | P0 disk and clone/auth |
| 9fts | online fresh | mesh worker, implementation/read-only | disk about 10 GB | timeout | route |
| new | online fresh | review/read-only backup worker | disk about 47.9 GB | timeout | route |
| primary-candidate | online fresh | primary/control standby, implementation/review | disk about 64.5 GB | reachable | dirty runtime repo |
| agent-01 | degraded fresh | codex/mimo worker | disk about 64.5 GB | timeout | degraded card |
| agent-02 | degraded fresh | codex/mimo worker | disk about 64.5 GB | timeout | degraded card |
| agent-03 | degraded fresh | codex/mimo worker | disk about 64.5 GB | timeout | degraded card |
| agent-04 | degraded fresh | mesh-only | no full card | timeout | limited telemetry |
| agent-05 | degraded fresh | mesh-only | no full card | timeout | limited telemetry |
| agent-06 | degraded fresh | mesh-only | no full card | timeout | limited telemetry |
| agent-07 | degraded fresh | mesh-only | no full card | timeout | limited telemetry |
| agent-08 | degraded fresh | mesh-only | no full card | timeout | limited telemetry |
| agent-09 | degraded fresh | mesh-only | no full card | timeout | limited telemetry |
| highload | degraded fresh | mesh-only/highload | no full card | timeout | limited telemetry |
| paris | degraded fresh | mesh-only/highload | no full card | timeout | limited telemetry |
| reserve242 | degraded fresh | mesh reserve | no full card | timeout | limited telemetry |
| server-kfrm | degraded fresh | mesh/FormulaLM candidate | no full card | timeout | limited telemetry |

## Readiness verdict

The cluster is visible to Control Plane, but not ready for broad autonomous execution until:

- `uiap` and `qjns` disk are fixed.
- direct/admin reachability is documented or restored.
- server GitHub auth is fixed.
- generic runner contract is hardened.
- dirty runtime repos are preserved/audited.
