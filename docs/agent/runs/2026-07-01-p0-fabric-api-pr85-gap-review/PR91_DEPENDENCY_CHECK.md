# PR91_DEPENDENCY_CHECK

Task: `2026-07-01-p0-fabric-api-pr85-gap-review`
Reviewer: `Алексей — Fabric API Reviewer`
Node: `primary-candidate:agent-host-primary`

PR #91: `p0/mimo-runner-output-auth-contract-repair-2026-07-01`
Known head from dispatcher ledger: `350544492ce14a12865fb9a04e2abf6f87c87d3f`

Assessment:

- PR #91 repairs MIMO runner output parsing and auth classification in Agent Host.
- It is useful before broad MIMO fanout and before relying on MIMO/API agents at scale.
- It is not a hard code dependency for PR #85's Control Plane/Fabric API endpoint repair.
- Both PR #85 and PR #91 remain draft and must not be merged automatically by this task.

Dependency decision: `not_blocking_pr85_repair`, but `required_before_broad_mimo_rollout`.
