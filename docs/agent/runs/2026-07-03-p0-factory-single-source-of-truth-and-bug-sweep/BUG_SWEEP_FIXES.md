# Bug Sweep Fixes

## Alias Target Matching

- Issue: aliases such as `home-live` and `mesh-home` could produce different answers.
- Root cause: routing compared raw node IDs.
- Files changed: `ops/factory_registry.py`, `ops/factory_control.py`, tests.
- Test added: canonical alias matching without `mesh-agent-*` drift.
- Risk: low.
- Rollback: revert branch.
- Result: aliases are matched through registry.

## Capability Alias Matching

- Issue: `devops` and `github_review` aliases were not enforced by one shared contract.
- Root cause: capability matching was exact string matching.
- Files changed: `ops/factory_registry.py`, `ops/factory_control.py`, tests.
- Test added: devops and review aliases.
- Risk: low.
- Rollback: revert branch.
- Result: aliases are explicit and bounded.

## Queue Diagnostics

- Issue: queue could be blocked without a structured reason endpoint.
- Root cause: no diagnostics API in baseline branch.
- Files changed: `ops/factory_control.py`, tests.
- Test added: unleaseable task diagnostics.
- Risk: medium; read-only endpoint, no queue mutation.
- Rollback: revert branch.
- Result: diagnostics explain leaseable/blocked status.

## Bounded Task Listing

- Issue: full task listing can be huge and slow.
- Root cause: `/v1/tasks` returned all tasks unless caller filtered by state.
- Files changed: `ops/factory_control.py`.
- Test added: covered by existing task contracts and py_compile.
- Risk: low; old no-query behavior preserved.
- Rollback: revert branch.
- Result: summary/compact callers can request bounded output.

## Backend Factory Status Proxy

- Issue: owner-facing `/api/factory/status` returned 503 and zero nodes.
- Root cause: backend used an old Control Plane URL/parser path and did not understand canonical health/fleet envelopes.
- Files changed: `backend/factory_status.py`, `tests/test_factory_status.py`.
- Test added: Fabric envelope plus queue diagnostics parser.
- Risk: medium; backend read-only status path.
- Rollback: restore `/var/backups/kolibri-p0-sot-20260703T123840Z/staging-backend/factory_status.py` and remove the backend URL drop-in.
- Result: live endpoint returns 200 with 135 nodes, 30 online, queue 17, blocked 0.

## Queue Diagnostics Performance

- Issue: live diagnostics could time out by scanning every historical task ID.
- Root cause: diagnostics loaded 21,964 task records to compute global state counts.
- Files changed: `ops/factory_control.py`.
- Test added: existing queue diagnostics regression plus live production check.
- Risk: low; read-only endpoint now reports queue-state counts instead of full historical state counts.
- Rollback: restore backed up `factory_control.py`.
- Result: live diagnostics response dropped to about 0.22s.

## Incomplete Fleet Registry API

- Issue: `/v1/fleet/registry` omitted reserve/agent physical servers, so agents could still receive an incomplete server foundation.
- Root cause: `fabric_node_catalog()` filtered canonical nodes to fallback/service nodes only.
- Files changed: `ops/factory_registry.py`, `tests/test_factory_registry.py`.
- Test added: `test_fabric_node_catalog_exposes_full_canonical_server_inventory`.
- Risk: low; read-only API now exposes documented canonical records and does not mark them online or scheduleable.
- Rollback: restore `/var/backups/kolibri-p0-network-foundation-20260703T134617Z/factory_registry.py` and restart `kolibri-factory-control.service`.
- Result: live `/v1/fleet/registry` returns 21 canonical nodes and includes `agent-10`, `reserve242`, reserve servers and reserve agents.
