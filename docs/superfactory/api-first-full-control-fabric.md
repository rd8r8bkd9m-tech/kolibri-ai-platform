# Superfactory API-First Full-Control Fabric

Task: `P0_API_FIRST_FULL_CONTROL_FABRIC_FINALIZE_2026_07_01`

The Kolibri superfactory control surface is API-first. Routine owner and agent operations must use protected Fabric API contracts for fleet status, routing, task submission, cancellation, draining, artifact lookup, bootstrap requests, and audit-backed owner control.

SSH is not a control plane. SSH is emergency-only and may be used only for first bootstrap, break-glass recovery, and diagnostics when the Fabric API is not yet installed or is unreachable. Any SSH recovery must end by restoring the protected Fabric API path.

## Required Control Guarantees

- API-first control: `ops/factory_control.py` exposes Fabric API health, policy, routes, relay, bootstrap, and key rotation contracts.
- No dead-end unavailable: agents must return structured `blocked` envelopes with `fallback_route`, `fallback_nodes`, `repair_task`, and `can_continue_elsewhere` instead of plain unavailable text.
- Fallback routing: direct Fabric API routes are preferred; unavailable targets can continue through `/v1/fabric/relay` when another eligible node is online.
- Owner full-control policy: owner control requires authentication, authorization, scoped permissions, audit logging, and credential rotation. The policy allows fleet read, route, task submit/cancel, node drain, artifact read, and bootstrap create operations.
- Node identity: every node has a stable non-secret `node_id`, process-level `agent_id`, and Russian display name for owner-facing reports.
- Key rotation: node credentials rotate on bootstrap, compromise suspicion, owner request, node reimage, and at least every 90 days. Overlap windows must be short and audited.
- New server bootstrap: bootstrap accepts non-secret metadata only and returns task metadata plus next API action with `secrets_returned: false`.
- Admin gates: privileged actions require authenticated API identity, authorization scope, audit context, and explicit safe-stub behavior where local execution would be unsafe.

## Implemented API Contracts

| Contract | Path | Status |
| --- | --- | --- |
| Fabric health | `GET /v1/fabric/health` | Implemented |
| Fabric policy | `GET /v1/fabric/policy` | Implemented |
| Fabric routes | `GET /v1/fabric/routes` | Implemented |
| Direct route resolution | `POST /v1/fabric/route` | Implemented |
| Safe relay | `POST /v1/fabric/relay` | Safe stub |
| Safe bootstrap | `POST /v1/fabric/bootstrap` | Safe stub |
| Key rotation policy | `GET /v1/fabric/keys/rotation` | Implemented |
| Filesystem integrity metadata | `GET /v1/filesystem` | Implemented |
| Fleet registry hygiene | `GET /v1/fleet/registry/hygiene` | Implemented |

## Fleet Identity

| Node | Russian display name | Role | Control path |
| --- | --- | --- | --- |
| `home` | `Связной` | command node gateway | Fabric API or fallback relay |
| `main` | `Директор` | control plane | Fabric API |
| `uiap` | `Знания` | knowledge/model node | Fabric API or fallback relay |
| `qjns` | `Тестировщик` | remote agent | Agent Host API or fallback relay |
| `9fts` | `Инженер` | implementation/model node | Agent Host API, model API, or fallback relay |
| `new` | `Ревьюер` | review agent | Agent Host API or fallback relay |

## Verification Expectations

Required finalization artifacts live under `docs/agent/runs/`. Each run report must include the task id, node, Russian display name, branch, commit, PR URL or blocker, tests, secret scan summary, artifact paths, blockers, and next action.
