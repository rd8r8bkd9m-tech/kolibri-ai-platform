# PLAN

Task: `P0_30MIN_12AGENT_02_FLEET_ONLINE_STEWARD_2026_07_02`
Agent: `Ирина - Fleet Online Steward`
Lease: `mesh-agent-02:agent-host-mesh-agent-02`
Remote worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-02/worktrees/P0_30MIN_12AGENT_02_FLEET_ONLINE_STEWARD_2026_07_02/P0_30MIN_12AGENT_02_FLEET_ONLINE_STEWARD_2026_07_02-attempt-1/repo`

## Timebox

- Created at: `2026-07-02T00:52:13.979553+00:00`.
- Required finish boundary: `2026-07-02T01:22:13.979553+00:00`.
- Final result must not be reported before that boundary unless the runner reports a timebox violation.

## Scope

Classify the live Control Plane fleet state, separate fresh working capacity from stale or duplicate cards, and produce the next safe repair queue for the 20-server always-online goal.

## Guardrails

- No product code changes.
- No secret, token, env, auth cache, or private key output.
- No destructive commands, restarts, firewall changes, VPN changes, credential rotation, or Git push.
- Count stale cards as metadata debt, not working capacity.
- Prefer Control Plane/Fabric API evidence over local assumptions.

## Work Steps

1. Confirm the remote lease and task envelope.
2. Read the fleet always-online policy and dispatcher queue context.
3. Query Control Plane node state.
4. Query Control Plane task state for this task.
5. Classify fresh, stale, degraded, duplicate, and busy nodes.
6. Create exact required artifacts: `PLAN.md`, `ACTIONS.md`, `RESULT.md`, and `NEXT.md`.
7. Recheck task state and artifact presence after the 30-minute boundary.
