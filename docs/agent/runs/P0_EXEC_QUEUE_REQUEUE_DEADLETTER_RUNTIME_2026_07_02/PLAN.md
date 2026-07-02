# PLAN

Task: `P0_EXEC_QUEUE_REQUEUE_DEADLETTER_RUNTIME_2026_07_02`

Goal: implement concrete queue, lease expiry, requeue, and dead-letter runtime behavior so tasks do not remain indefinitely stuck.

Plan:

1. Inspect the existing factory control queue and Agent Host lease/failure paths.
2. Add concrete reconciliation semantics for expired leases.
3. Expose reconciliation results through runtime status surfaces.
4. Add focused tests for requeue, dead-letter, duplicate prevention, and status reconciliation.
5. Run targeted verification and record full-suite blockers without printing secrets.

