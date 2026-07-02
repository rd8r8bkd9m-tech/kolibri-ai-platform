# Next

Canary plan:

1. Deploy this branch to one non-owner server node running Control Plane and one Agent Host.
2. Start Control Plane with conservative defaults:
   `FACTORY_MAX_HTTP_WORKERS=64 FACTORY_LEASE_QUEUE_SCAN_LIMIT=100 FACTORY_LEASE_REAPER_BATCH_LIMIT=250 FACTORY_LEASE_REAPER_INTERVAL=5`.
3. Start Agent Host with jitter defaults:
   `KOLIBRI_LEASE_IDLE_MIN=1 KOLIBRI_LEASE_IDLE_MAX=15 KOLIBRI_LEASE_EMPTY_BACKOFF_FACTOR=1.35 KOLIBRI_MAX_INFLIGHT=1`.
4. Seed 1000 logical no-op/read-only tasks through the Control Plane API without starting 1000 host processes.
5. Run 20 minutes of lease polling and verify:
   `/v1/health` returns within 250 ms p95,
   `/v1/tasks?limit=100` returns within 500 ms p95,
   process fd count stays below 256,
   thread count stays below `FACTORY_MAX_HTTP_WORKERS + 10`,
   no more than configured Agent Host processes are present.
6. If stable, canary 3 nodes, then raise logical task volume to 2000 while keeping physical hosts bounded.

Next exact deploy/canary task:

`P0_DEPLOY_CONTROL_PLANE_1000_AGENT_CAPACITY_CANARY_2026_07_02`: deploy this branch to one server node, run the 1000 logical read-only task canary, capture fd/thread counts, health/task p95 latencies, Redis connected clients, and rollback decision.

Blockers:

- Full `pytest` collection on this server is blocked by missing backend dependencies: `pydantic`, `httpx`.
- Remote branch push and PR creation are blocked on this server because the configured SSH key is read-only: `ERROR: The key you are authenticating with has been marked as read only.`
- `gh` is not available on PATH, so there is no connector-free fallback PR creation path from this server.
