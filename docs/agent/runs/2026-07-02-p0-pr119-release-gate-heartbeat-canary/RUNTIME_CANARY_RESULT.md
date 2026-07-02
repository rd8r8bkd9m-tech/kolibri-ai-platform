# RUNTIME_CANARY_RESULT

Status: blocked_not_run

No canary tasks were submitted.

Reason:

- PR119 release gate decision is `blocked`.
- Control Plane health/status probes timed out before deploy.
- Recent Factory Control logs showed lease endpoint 500s.

Required canaries after unblock:

1. MIMO canary: direct MIMO runner heartbeat path.
2. Codex/API/generic canary: long-running Codex/API/generic subprocess heartbeat path.
3. FormulaLM/crawler-like canary: crawler-like long task heartbeat path, without full FormulaLM wave.

Pass criteria for each future canary:

- Unique `task_id`.
- Runtime longer than one normal lease duration when feasible.
- Multiple task heartbeats during execution.
- `lease_until` refresh before expiry.
- Structured artifact including terminal state.
- Not moved to `dead_letter` due to `lease_expired`.
- Auth/provider unavailability classified as `blocked_auth` or `provider_runtime`, not faked as success.
