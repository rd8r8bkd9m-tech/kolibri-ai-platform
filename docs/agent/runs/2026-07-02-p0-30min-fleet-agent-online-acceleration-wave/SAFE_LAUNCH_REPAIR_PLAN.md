# Safe Launch And Repair Plan

Task: `P0_30MIN_FLEET_AGENT_ONLINE_ACCELERATION_WAVE_2026_07_02`

This plan is safe-by-default: it describes what to launch or repair next, but this wave did not perform destructive or service-mutating actions.

## Immediate Safe Routing

| Work type | Safe targets | Conditions |
|---|---|---|
| Implementation | `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`, `mesh-9fts`, constrained `main`, constrained `primary-candidate` | Use small tasks, exact artifacts, focused tests, no broad deploys |
| Review | `new`, `main`, `qjns`, `mesh-agent-01..03` | Avoid heavy builds on low-memory nodes |
| QA/read-only smoke | `new`, `main`, `mesh-agent-01..03`, `uiap`, `qjns` | Read-only unless a scoped repair task authorizes mutation |
| RAG/knowledge | `uiap` | Keep CPU/light workload limits |
| Owner/home orchestration | none until `home` and `home-live` return fresh | Respect Telegram single-receiver ownership; no gateway start from this task |
| Model/MIMO | `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`, `mesh-9fts` | Only through approved credentials and provider policy |

## Do Not Target For New Work

- Stale metadata cards: `agent-01..09`, `9fts`, `highload`, `paris`, `reserve242`, `server-kfrm`, `smoke-primary`.
- Stale mesh shadows: `mesh-agent-04..09`, `mesh-highload`, `mesh-home`, `mesh-main`, `mesh-new`, `mesh-paris`, `mesh-primary`, `mesh-qjns`, `mesh-reserve242`, `mesh-server-kfrm`, `mesh-uiap`.
- `home` and `home-live` while `/v1/nodes` reports stale heartbeat.

## Safe Repair Backlog

1. Heartbeat/card freshness repair for `home` and `home-live`.
   - First action: read-only Agent Host and Control Plane heartbeat inspection.
   - Forbidden in first pass: service restart, credential mutation, filesystem cleanup.
2. Stale mesh shadow/card reconciliation.
   - First action: compare canonical server cards with mesh bridge output and identify duplicate/stale identities.
   - Forbidden in first pass: deleting cards or changing retention without owner approval.
3. Queue retention audit.
   - Current queue includes old `KOL-CLUSTER-*` and MIMO probe tasks.
   - First action: read-only classification by age, target, and obsolete status.
   - Forbidden in first pass: cancelling or archiving tasks without explicit owner approval.
4. `qjns` credential/runner reclassification.
   - Current live card is fresh online but lacks runner capability.
   - First action: credential-safe smoke task that reports only pass/fail classes.
   - Forbidden: printing tokens, interactive login, push attempts to protected branches.
5. `uiap` runner capability classification.
   - Keep as RAG/knowledge node until a scoped task proves runner readiness.
6. Fabric route parity repair for `10.99.0.2`.
   - `10.99.0.2` serves health/nodes/tasks but not Fabric routes in the observed check.
   - First action: read-only route mount/version comparison against `10.99.0.10`.

## Launch Sequence For Next Wave

1. Keep current four acceleration wave tasks running until they finish or produce artifacts.
2. Dispatch only read-only repair-classification envelopes for stale/blocked nodes.
3. Prefer fresh runner nodes for implementation backlog: `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`.
4. Use `main` and `primary-candidate` for constrained orchestration, not heavy fanout.
5. Route review/QA to `new`, `qjns`, and fresh mesh agents.
6. Do not increase logical-agent fanout until queue retention and provider limits are classified.
