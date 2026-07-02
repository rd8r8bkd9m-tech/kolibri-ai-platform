# Runtime Validation Plan

Do not run the full MIMO/FormulaLM wave yet.

Next task: `P0_CONTROL_PLANE_LEASE_STORM_RUNTIME_CANARY_2026_07_02`

Stages:

1. Deploy to `primary-candidate` only.
2. Verify baseline with the reduced worker pool.
3. Run a 20 logical-agent poll canary.
4. Increase to 50, 100, 250, 500, then 1000 logical agents.
5. At each stage record fd count, thread count, Redis clients, lease errors, health p95, task listing p95.
6. Keep physical Agent Host processes bounded.
7. Roll back immediately if fd/thread growth, 5xx rate, or p95 latency crosses the gate.

Only after this canary passes:

- Retry PR #119 release gate.
- Consider restoring the stopped local worker services gradually.
- Consider requeueing MIMO/FormulaLM work.
