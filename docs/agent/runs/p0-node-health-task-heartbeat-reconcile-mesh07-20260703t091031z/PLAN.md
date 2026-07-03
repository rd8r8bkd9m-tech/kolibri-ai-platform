# Plan

- Repair `/v1/nodes` node health projection so fresh active task heartbeat can keep active workers visible as online.
- Keep reconciliation bounded to active task states with fresh heartbeat and unexpired lease.
- Preserve original stale node heartbeat evidence on the node card.
- Add runtime tests for fresh active task recovery and expired task non-recovery.
- Verify focused runtime tests and record any environment blockers.

