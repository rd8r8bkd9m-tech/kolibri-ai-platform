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

## Agent-10 Registry-Only Masking

- Issue: after the full registry API fix, `agent-10` was visible in fleet APIs but still had no real Control Plane heartbeat, which could hide the provider/network outage.
- Root cause: drift diagnostics counted synthetic registry catalog records as Control Plane-present records.
- Files changed: `ops/factory_registry.py`, `ops/factory_control.py`, `tests/test_factory_registry.py`, `tests/test_fabric_control.py`.
- Test added: registry-only records remain missing in Control Plane until a heartbeat arrives.
- Risk: low; read-only diagnostics and non-scheduleable quarantine metadata only.
- Rollback: restore `/var/backups/kolibri-agent10-drift-fix-20260703T140705Z` and `/var/backups/kolibri-agent10-quarantine-20260703T140745Z`.
- Result: live `/v1/fleet/drift` reports `agent-10` as missing and registry-only; live `/v1/fleet/registry` marks it `quarantined`, `provider_network_unreachable`, `safe_to_schedule=false`.

## SSH Access Path Metadata

- Issue: agents and owner commands had to remember ad hoc external/internal SSH paths.
- Root cause: registry did not expose canonical SSH access mode, jump host, target IP and identity policy.
- Files changed: `ops/factory_registry.py`, SSH topology generator.
- Test added: registry exposes `ssh_access` for representative direct, internal-via-home, internal-via-main and external-via-main nodes.
- Risk: low; metadata only plus local/generated SSH config.
- Rollback: restore `/var/backups/kolibri-ssh-access-registry-20260703T161203Z`.
- Result: live `/v1/fleet/registry` returns `ssh_access`; `ssh kolibri-home`, `ssh kolibri-main`, and `ssh kolibri-qjns` work by key.

## SSH Trust Bootstrap

- Issue: the command node could not reliably enter every root-managed canonical server by one alias/key format.
- Root cause: local deploy public keys were not consistently present in target `/root/.ssh/authorized_keys`, and external-only VPS records needed the `main` jump path from the command node.
- Files changed: live SSH trust on reachable targets with per-host `authorized_keys` backups; documentation matrix updated.
- Test added: sequential alias verification from the command node for all 21 canonical server aliases.
- Risk: medium; root SSH trust was changed on reachable infrastructure, with backups made before edits.
- Rollback: restore the per-host `/root/.ssh/authorized_keys.backup-kolibri-bootstrap-*` file on the affected host.
- Result: 21 of 21 canonical server aliases work from the command node by key. `agent-10` uses the internal mesh target `10.99.0.18`.

## Agent-10 Mesh Management Route

- Issue: physical `agent-10` was incorrectly documented and registered as quarantined after the mesh route came back.
- Root cause: registry only knew the external IP `217.60.38.191`; live SSH and heartbeat use `10.99.0.18` over `wg-kolibri`.
- Files changed: `ops/factory_registry.py`, SSH topology generator, source-of-truth docs, tests.
- Test added: `agent-10` registry asserts internal IP `10.99.0.18` and `internal_via_main` SSH access.
- Risk: low; source-of-truth and generated SSH target update only.
- Rollback: restore previous registry and SSH topology if `10.99.0.18` stops heartbeating.
- Result: `ssh agent-10` reaches `kolibri-hk-edge-load` as `root`; Agent Host is active.
