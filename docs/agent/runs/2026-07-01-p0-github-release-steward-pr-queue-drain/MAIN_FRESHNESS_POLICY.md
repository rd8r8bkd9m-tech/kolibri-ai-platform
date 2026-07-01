# Main Freshness Policy

Incident:

- PR #95 merged at `2026-07-01T19:05:12Z`.
- `main` advanced from `6d0317c52a9694448ee2c352dc196ce7a27b9487` to `a0d34d6d97a1a2af90463a1205649a24b4a178d7`.
- Many prepared PRs still had release evidence against the older base.

Policy:

- After every merge to `main`, re-check every candidate PR against the new `main`.
- Treat docs-only PRs as serial release train cars.
- Keep runtime PRs behind explicit owner release gates and canary tasks.
- Do not use old mergeability or old green CI as final release evidence after `main` moves.
- Maintain a living PR queue matrix so the next steward does not rediscover the queue from scratch.
