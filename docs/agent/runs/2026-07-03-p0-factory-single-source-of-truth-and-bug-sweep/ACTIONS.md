# Actions

## Completed In This Branch

- Added `ops/factory_registry.py`.
- Replaced hard-coded Control Plane node catalog with shared registry output.
- Added canonical node matching for `home-live`, `mesh-home`, `primary`, `mesh-primary`, `rag`, `tools`, `inference` and `worker-backup`.
- Preserved logical worker identity for `mesh-agent-*`; it is not aliased to physical `agent-*`.
- Added explicit capability alias matching for `devops`, `github_review`, `review`, `runner:codex`, `runner:mimo` and `runner:api`.
- Added `/v1/fleet/summary`, `/v1/fleet/registry`, `/v1/fleet/drift`, `/v1/registry/validate`.
- Added `/v1/tasks/queue/diagnostics`.
- Added bounded `/v1/tasks?summary=1&compact=1&limit=N` response path.
- Added regression tests for registry, routing aliases, capability aliases and diagnostics.

## Live Facts Used

- Control Plane live `/v1/nodes` snapshot: 135 records, 32 fresh, 103 stale, 28 online, 4 degraded.
- Logical mesh-agent records: 101 in Control Plane snapshot.
- Systemd logical workers found: 20 active `kolibri-agent-host@mesh-agent-01..20`, 81 inactive units.
- Live `/v1/tasks?summary=1&compact=1&limit=20`: queue 18, blocked 9, task ids 21964.
- Live `/v1/tasks/queue/diagnostics`: 404 before this branch.
- `10.99.0.10:5173` and `10.99.0.10:19132` returned HTTP 200, but Home kiosk deploy tasks were still queued.
- Local Telegram gateway was standby/inactive while failover guard observed primary healthy.

