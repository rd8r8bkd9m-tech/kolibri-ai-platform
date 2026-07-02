# Plan

Task: `P0_AUTOPILOT_EXTRA_33_PARIS_HIGHLOAD_READINESS_2026_07_02`

Agent: `agent-host-mesh-agent-33`

Node: `mesh-agent-33`

Owner-facing agent name: `Дмитрий — Fleet Engineer`

Scope: read-only readiness probe for `hostvds-paris-highload` / Paris highload reserve.

## Constraints

- Run from assigned server-side mesh worker, not from a local Mac product implementation path.
- Do not print secrets, environment files, private keys, tokens, or process command lines that may contain credentials.
- Do not use destructive git commands, force push, or push to main.
- Do not modify product code.
- Keep checks bounded and lightweight.

## Steps

1. Inspect local dispatcher docs and SSH topology for `hostvds-paris-highload`.
2. Probe target SSH reachability with public-key-only, short-timeout SSH.
3. Probe fallback server route through `kolibri-primary-codex`.
4. Query Control Plane health, node cards, route data, and this task record.
5. Capture assigned worker resource budget and API routing health.
6. Record blocker and next exact task.

