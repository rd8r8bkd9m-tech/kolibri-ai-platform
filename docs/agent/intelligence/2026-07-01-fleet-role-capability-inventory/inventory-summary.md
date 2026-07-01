# Inventory Summary

Task: `P0_FLEET_ROLE_CAPABILITY_INVENTORY_2026_07_01`
Generated: `2026-07-01T13:14:29.380888+00:00`

## Control Plane

| Field | Value |
|---|---|
| Status | `ok` |
| Queue backend | `redis` |
| Redis | `PONG` |

## Card Counts

| Class | Count |
|---|---:|
| Total visible cards | 42 |
| Fresh cards | 8 |
| Online cards | 8 |
| Owner-facing server nodes | 7 |
| Mesh shadow cards | 20 |
| Stale metadata cards | 15 |

## Safe Target Pools

| Pool | Targets |
|---|---|
| Implementation | `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`, `mesh-9fts`, `main for small/staging changes only`, `primary-candidate after heartbeat repair` |
| Review | `main`, `new`, `primary-candidate after heartbeat repair` |
| QA | `new`, `main`, `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03` |
| RAG/knowledge | `uiap` |
| Telegram | `no fresh current Telegram-specialized target`, `primary-candidate after heartbeat repair`, `home-live after heartbeat repair` |
| Observability | `main`, `uiap`, `qjns`, `new`, `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`, `mesh-9fts` |
| Canary deploy | `main for staging/API only`, `mesh-9fts for inference recovery only`, `uiap for RAG-only canary after runner repair` |
| Model/LLM | `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`, `primary-candidate after heartbeat repair`, `home after heartbeat repair` |

## Next Action

Repair `qjns` runner/GitHub/MIMO credentials and restore `primary`/`home` heartbeat freshness before assigning owner-facing or Telegram work; then verify `main` runner auth, retire stale mesh/metadata cards, and clean `qjns`/`uiap` queue retention.
