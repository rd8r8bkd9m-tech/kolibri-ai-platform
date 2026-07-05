# RESULT.md

## P0 Restore Runtime and Prove Start Factory

### Completed Phases

| Phase | Status | Notes |
|-------|--------|-------|
| 1. Runtime baseline | DONE | 117 nodes, 298 tasks, single CP alive |
| 2. Control Plane authority | DONE | home:9101 authoritative, main/primary dead |
| 3. Agent Host heartbeat | DONE | Fixed control URLs, fleet 5→74 online |
| 4. Running index drift | NOTED | 12 phantom running, needs separate rebuild |
| 5. Execution contract | NOTED | Available in ops/agent_host.py, needs import |
| 6. Submit/lease/artifact | FIXED | Lease pipeline works after killing duplicate |
| 7. Start Factory proof | PROVEN | Full cycle: submit→lease→execute→artifact→complete |
| 8. Artifact proof | PROVEN | /tmp/PROOF.md exists, 221 bytes, content-bearing |
| 9. Home NOC state | YELLOW | CP healthy, execution now works |
| 10. Tests | NOT RUN | Blocked by test env setup |
| 11. PR | NOT CREATED | Needs commit first |

### Remaining Blockers

1. Running index drift (12 phantom tasks) — needs P0_QUEUE_RUNNING_INDEX_REBUILD
2. 3 mesh nodes offline (9fts/uiap/new) — VPN tunnel broken
3. Tests not run yet
4. PR not created

### Next P0 Task

P0_QUEUE_RUNNING_INDEX_REBUILD_WITH_BACKUP_20260704
