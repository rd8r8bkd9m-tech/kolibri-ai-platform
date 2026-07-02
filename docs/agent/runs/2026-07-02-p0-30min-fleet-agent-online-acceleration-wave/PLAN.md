# Plan

Task: `P0_30MIN_FLEET_AGENT_ONLINE_ACCELERATION_WAVE_2026_07_02`

Role: `autonomous_engineer`

Execution node:

- Host: `kolibri`
- Worktree: server-side Control Plane lease worktree under `/var/lib/kolibri-agent/...`
- Branch: `agent/P0_30MIN_FLEET_AGENT_ONLINE_ACCELERATION_WAVE_2026_07_02/generic`
- Mode: read-only remote fleet acceleration wave and docs-only artifact output.

Guardrails:

- Do not run on a local Mac dispatcher.
- Do not change product code.
- Do not restart, drain, cancel, delete, rotate credentials, mutate firewall/VPN, or change service state.
- Do not print secrets.
- Use live Control Plane APIs for classification and produce a safe launch/repair plan.

Timebox:

- Start: `2026-07-02T00:17:35Z`
- Target duration: 30 minutes.
- Probe cadence: roughly every 5 minutes.
- Final result must wait for the timebox to complete.

Method:

1. Read prior fleet inventory, always-online policy, and dispatcher status artifacts.
2. Probe Control Plane endpoints from the server node:
   - `http://10.99.0.10:9101/health`
   - `http://10.99.0.10:9101/v1/nodes`
   - `http://10.99.0.10:9101/v1/fleet/nodes`
   - `http://10.99.0.10:9101/v1/fabric/routes`
   - `http://10.99.0.10:9101/v1/tasks`
   - fallback checks on `http://10.99.0.2:9101`
3. Classify fresh online capacity, stale cards, blocked/repair-required route entries, and role-specific target pools.
4. Record the active acceleration wave tasks already leased by Control Plane.
5. Produce a safe launch/repair plan without performing destructive repair actions.

