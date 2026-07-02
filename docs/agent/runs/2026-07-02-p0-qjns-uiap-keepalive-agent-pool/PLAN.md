# Plan

Task: `P0_PRODUCT_QJNS_UIAP_KEEPALIVE_AND_AGENT_POOL_2026_07_02`

1. Reuse Agent Host as the keepalive and worker-pool authority instead of adding a second daemon.
2. Gate qjns/uiap worker capabilities on disk, memory, max inflight and MIMO availability.
3. Persist readiness through Control Plane register, heartbeat and lease paths.
4. Add a non-secret preflight command for operator deployment.
5. Verify with focused Agent Host and Control Plane tests.
