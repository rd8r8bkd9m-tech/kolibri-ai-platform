# Safe Target Pools

Task: `P0_FLEET_ROLE_CAPABILITY_INVENTORY_2026_07_01`
Generated: `2026-07-01T13:14:29.380888+00:00`

| Pool | Primary targets | Use for | Avoid |
|---|---|---|---|
| Implementation | `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`; constrained: `mesh-9fts`, `main`; after heartbeat repair: `primary-candidate` | Repo changes, tests, small contracts, artifact-backed implementation | `qjns` until GitHub/MIMO repaired; stale metadata cards; stale mesh shadows |
| Review | `main`, `new`; after heartbeat repair: `primary-candidate` | Independent review, PR risk checks, test-gap review | Heavy builds on `main`; stale `mesh-new` |
| QA | `new`, `main`, `mesh-agent-01..03` | Read-only QA, smoke/regression tests, staging checks | Production deploys during inventory |
| RAG/knowledge | `uiap` | ChromaDB/embeddings/knowledge checks and RAG-specific maintenance | General implementation or GitHub push until runner capability is verified |
| Telegram | No fresh current Telegram-specialized target; after heartbeat repair: `primary-candidate`, `home-live` | Owner-facing Telegram orchestration and chat response tasks | Non-orchestrator mesh cards and metadata-only cards |
| Observability | `main`, `uiap`, `qjns`, `new`, `mesh-agent-01..03`, `mesh-9fts` | Health checks, read-only diagnostics, queue/card reconciliation | Drains, restarts, deploys, credential disclosure |
| Canary deploy | `main` for API/frontend staging only; `mesh-9fts` for inference recovery only; `uiap` for RAG-only after runner repair | Narrow canaries with explicit target and rollback | Owner gateway/home, stale cards, broad fleet deploys |
| Model/LLM | `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`; after repair: `primary-candidate`, `home` | Codex/MIMO/model orchestration, moderate local runner work | `main`, `qjns`, `uiap`, low-memory 1-vCPU cards unless task is specialized |

Selection rule: prefer fresh online cards with explicit runner capabilities for code-changing work. Use specialized nodes only for their role-specific workload.
