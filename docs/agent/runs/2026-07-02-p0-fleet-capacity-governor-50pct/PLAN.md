# Plan

Task: `P0_FLEET_CAPACITY_GOVERNOR_50PCT_2026_07_02`

1. Reuse the existing fleet inventory and always-online policy as the source
   for safe target classification.
2. Produce a temporary two-hour 50 percent capacity-governor contract with
   explicit per-node worker budgets.
3. Define safe workload lanes, throttle/drain policy, overload stop conditions,
   and monitoring commands.
4. Record the canonical task result fields:
   `task_id`/`status`/`lease_owner`/`artifacts`/`blockers`/`next_action`.
5. Verify that the required run artifacts exist and no destructive command was
   needed.

No live drain, restart, cancel, credential, push, or production mutation is part
of this plan.

