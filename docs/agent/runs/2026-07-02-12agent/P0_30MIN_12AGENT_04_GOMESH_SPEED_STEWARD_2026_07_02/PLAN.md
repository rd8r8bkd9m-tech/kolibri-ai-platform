# P0_30MIN_12AGENT_04_GOMESH_SPEED_STEWARD_2026_07_02 Plan

Agent: Николай - GoMesh Speed Gate Steward
Task type: remote read-only speed-gate stewardship
Node evidence: Control Plane lease owner `mesh-agent-03:agent-host-mesh-agent-03`
Worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-03/worktrees/P0_30MIN_12AGENT_04_GOMESH_SPEED_STEWARD_2026_07_02/P0_30MIN_12AGENT_04_GOMESH_SPEED_STEWARD_2026_07_02-attempt-1/repo`

## Constraints

- Remote/server execution required; no local Mac implementation.
- Work for the 30-minute timebox before final result, or report a runner timebox violation.
- No product code changes.
- No secrets, keys, PSKs, tokens, cookies, or env dumps in artifacts.
- No destructive git, network, routing, service, or whole-LAN changes.

## Stewardship Plan

1. Confirm the task is running under the Control Plane on `mesh-agent-03`.
2. Confirm the elapsed task window is at least 30 minutes before final reporting.
3. Use existing repository evidence for GoMesh speed gate state.
4. Preserve selector/LAN promotion block until a fresh 300+ Mbps GoMesh canary passes.
5. Produce exact next tasks and blockers for the next remote agent.

