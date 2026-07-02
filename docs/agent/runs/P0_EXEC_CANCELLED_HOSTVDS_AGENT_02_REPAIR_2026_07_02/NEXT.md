# Next

Immediate next task:

`P0_REPAIR_HOSTVDS_AGENT_02_TARGETED_LEASE_AND_FABRIC_ROUTE_2026_07_02`

Exact command:

```bash
python3 ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_REPAIR_HOSTVDS_AGENT_02_TARGETED_LEASE_AND_FABRIC_ROUTE_2026_07_02.json
```

Required envelope behavior:

- Target a fresh implementation node, preferably `mesh-agent-02` only after confirming it has no active task.
- Do not target stale `agent-02`.
- Preflight live Factory Control route surface:
  - `GET /health`
  - `GET /v1/health`
  - `GET /v1/fabric/health`
  - `GET /v1/fabric/routes`
  - `POST /v1/fabric/route`
- If route endpoints are still `404`, perform a scoped reversible deploy/restart of `kolibri-factory-control.service` from `/opt/kolibri-ai-platform`, with backup and rollback path.
- After route repair, submit a read-only redacted readiness probe to `mesh-agent-02`.
- The probe must record node card freshness, active task state, disk/memory summary, runner capabilities, and GitHub auth classification without printing tokens or credential helper contents.
- Cancel or archive old stale `target_node=agent-02` queued tasks only with owner-approved queue retention policy.

Acceptance for the next task:

- `/v1/fabric/routes` returns HTTP 200 from the same route used by `ops/kolibri-dispatch`.
- `/v1/fabric/route` returns either a direct `mesh-agent-02` route or a structured blocked envelope with fallback nodes and repair task.
- Exact `mesh-agent-02` readiness probe runs on `mesh-agent-02`, not another logical worker.
- Result artifacts include rollback command if a service restart was performed.
