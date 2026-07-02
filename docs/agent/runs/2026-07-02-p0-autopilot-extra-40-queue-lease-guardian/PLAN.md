# Queue Lease Guardian Plan

Task id: `P0_AUTOPILOT_EXTRA_40_QUEUE_LEASE_GUARDIAN_2026_07_02`

Node: `mesh-agent-40` server-side logical worker.
Agent: `autonomous_engineer`.

1. Inspect the existing Factory Control queue, lease, idempotency, retry and dead-letter contracts.
2. Add a reusable, Redis-independent queue guardian inspection contract.
3. Expose safe runtime inspection through the Control Plane API and dispatcher CLI.
4. Generate idempotent repair task envelopes without performing destructive queue mutation by default.
5. Verify with focused tests and syntax checks.

