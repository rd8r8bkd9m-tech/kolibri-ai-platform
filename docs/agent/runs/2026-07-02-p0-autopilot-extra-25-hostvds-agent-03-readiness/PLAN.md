# Plan

Task: `P0_AUTOPILOT_EXTRA_25_HOSTVDS_AGENT_03_READINESS_2026_07_02`

Agent: `Алексей - HostVDS Agent 03 Readiness Steward`

Execution node: `mesh-agent-25` on server host `kolibri`.

Target: `hostvds-agent-03` / `agent-03` / mesh shadow `mesh-agent-03`.

## Scope

1. Prove server-side execution and avoid local Mac/product-code changes.
2. Probe target readiness through available safe routes:
   - direct SSH bootstrap diagnostic,
   - Factory Control `/v1/nodes`,
   - Fabric route API,
   - control-plane route health,
   - disk and runner status from the node card.
3. Check GitHub auth/tooling status without printing tokens or environment.
4. Classify blockers and produce the next exact repair task.

## Safety

- No secrets, environment dumps, private keys, token values, cookies, or credential files printed.
- No destructive git commands.
- No force push, no push to main, no merge.
- No service restart or live runtime mutation.
- Artifact-only repository writes under this run directory.
