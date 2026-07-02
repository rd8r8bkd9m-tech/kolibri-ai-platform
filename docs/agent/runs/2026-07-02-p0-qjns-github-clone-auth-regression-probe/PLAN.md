# P0 QJNS GitHub Clone/Auth Regression Probe Plan

Task: `P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02`

Execution node: `kolibri`, under server Agent Host lease `mesh-agent-14`.

Target node: `qjns` / `agent-host-qjns`.

Plan:

1. Confirm this work is running on a server Agent Host worktree, not a local Mac.
2. Query Control Plane health, qjns node card, and qjns route.
3. Run only redacted, noninteractive GitHub probes; do not print secrets.
4. Dispatch qjns-hosted read-only probe through Control Plane.
5. Dispatch a bounded qjns clone-phase canary using `review_pr` with a deliberately missing branch. Expected repaired-auth signal: `git clone` succeeds, then `git fetch origin __kolibri_probe_missing_ref_20260702_no_checkout__` fails.
6. Record exact state, artifacts, blockers, and next action.

Forbidden actions observed:

- No interactive login.
- No secret printing.
- No destructive git command.
- No force push.
- No push to `main`.
- No credential creation or rotation.
