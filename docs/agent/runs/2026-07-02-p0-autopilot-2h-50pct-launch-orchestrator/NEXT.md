# Next

1. Repair or reassign `P0_AUTOPILOT_50PCT_CAPACITY_GOVERNOR_2026_07_02`; `main` failed with Codex auth refresh / HTTP 401.
2. Repair qjns Agent Host runner availability before relying on qjns for Codex child tasks; `P0_AUTOPILOT_GUARDIAN_RUNNER_CONTRACT_STEWARD_2026_07_02` failed with `runner_unavailable`.
3. Let the queued readiness matrix and Control Plane steward tasks lease on server Agent Hosts.
4. Keep PR #105 under owner merge gate; the steward task is read-only and must not merge, approve, mark ready, push, or force push.
5. Scale down if the governor reports stale-node inclusion, lease churn, unbounded fanout, or missing readiness matrix evidence.
