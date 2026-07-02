# Next

Task: `P0_FLEET_CAPACITY_GOVERNOR_50PCT_2026_07_02`

Recommended next action:

Activate the governor only if the owner or Control Plane operator confirms the
two-hour window. During the window, admit new work according to
`CAPACITY_GOVERNOR_50PCT.md`, keep stale cards at zero capacity, and run only
read-only monitoring unless a separate scoped repair task authorizes live
mutation.

Follow-up tasks:

- Add a scheduler-level feature flag for `temporary_50pct_capacity_governor`
  if the policy needs automatic enforcement rather than operator procedure.
- Add a read-only capacity dashboard view that shows active leases versus the
  temporary budget per node.
- Re-run fleet inventory after the two-hour window and record whether normal
  capacity can resume.

