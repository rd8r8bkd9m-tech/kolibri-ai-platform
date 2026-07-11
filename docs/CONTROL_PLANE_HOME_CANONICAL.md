# Canonical Control Plane on Home

Status: owner directive and implementation invariant, 2026-07-10.

## Decision

`home` is the single canonical Control Plane identity for Kolibri AI OS.
Historical Control Plane processes or endpoints on `main`, `primary`,
`primary-candidate` or other nodes are not used for scheduling, task state,
release decisions, UI aggregation or failover. Those machines may remain
ordinary workers after passing the same Agent Host health and capability gates
as every other node.

This decision does not alter the known-good 21-server Mac/Home bootstrap or the
mesh. It changes application routing and authority only.

## Runtime contract

- On Home, the compatibility Control Plane listens locally on port `9101`.
- Services receive the canonical URL through runtime configuration or the
  signed fleet manifest. Application code must not embed an old IP address.
- Home-local services use the loopback endpoint. Mac and workers use the Home
  service endpoint published by the manifest over an already trusted route.
- The public Shell talks only to the unified backend gateway. It never selects
  or exposes a Control Plane endpoint.
- `/control` reports Control Plane provenance as `control-plane/home` and keeps
  provider provenance separate.
- When Home Control Plane is unavailable, control mutations fail closed and
  expose an actionable degraded state. They do not silently route to a legacy
  Control Plane.

## Canonical fleet view

The live `peers` projection in Home's replicated mesh manifest is the
authority for physical factory membership. Redis `node_ids` and Agent Host
cards are runtime observations and an append-only audit source; they cannot
add a physical server to the scheduler.

- `GET /v1/nodes` and `GET /v1/nodes?scope=active` return exactly one row per
  canonical manifest member.
- A canonical member without a fresh Agent Host observation remains visible as
  `quarantined`, `freshness=stale`, `schedulable=false`; it is never reported
  online.
- `scope=audit` returns Redis-only legacy, duplicate and shadow identities as
  archived historical records. `scope=all` returns both projections for an
  operator investigation.
- Fleet routing, leases, provider candidates, release inventory and
  `/api/factory/status` consume only `scope=active`.
- No reconciliation deletes historical Redis evidence. Removal from active
  membership happens through the authenticated mesh tombstone protocol.
- If the manifest is missing, malformed or ambiguous, membership reads return
  an explicit unavailable state and task leasing fails closed.

## Migration rule

1. Take read-only inventory and checksum snapshots of current Home services.
2. Verify Home task, node, lease and event contracts locally.
3. Point the compatibility backend, release controller and operator UI to Home.
4. Run a real task and verifier canary through Home.
5. Remove legacy Control Plane endpoints from runtime configuration and routing.
6. Keep old processes stopped or isolated until their data is reconciled and
   retained according to the migration policy; do not delete evidence.

Provider routing remains independent: Mimo, Codex and other execution providers
may fail over according to policy while task authority stays on Home.
