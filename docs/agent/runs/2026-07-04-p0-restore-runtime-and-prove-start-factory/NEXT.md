# NEXT.md

## Immediate Next Tasks

1. **P0_QUEUE_RUNNING_INDEX_REBUILD** — Fix 12 phantom running tasks
2. **P0_VPN_TUNNEL_REPAIR** — Restore 9fts/uiap/new connectivity
3. **P0_TESTS_RUN** — Execute test suite
4. **P0_PR_CREATE** — Create draft PR with all fixes

## Architecture Decisions

- Single factory-control process on home (kill duplicates)
- All agent-host → 10.99.0.1:9101 (never 10.99.0.2)
- Lease pipeline: submit→queue→lease→execute→artifact→complete (proven)
