# Tests

Verification commands run:

```bash
git status --short --branch
```

Result: clean before this docs-only artifact update; branch was `agent/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02/generic...origin/main`.

```bash
python3 ops/kolibri-dispatch doctor
```

Result:

- Control Plane health passed: `status=ok`, Redis `PONG`.
- Repository check passed.
- Local `gh` binary is unavailable in this worker.
- Default SSH diagnostics to `9fts` and `new` timed out; not used as the management path.

```bash
python3 ops/kolibri-dispatch nodes
```

Result:

- Legacy `agent-02` card is stale with heartbeat from `2026-06-30T11:56:41.610287+00:00`.
- Live `mesh-agent-02` card is fresh/online, maps to `mesh_source_node_id=agent-02`, has `runner:codex` and `runner:mimo`, 8 CPU, and about 52 GB free disk in the observed node snapshot.

```bash
python3 ops/kolibri-dispatch fabric-route hostvds-agent-02 --required-capability implementation
python3 ops/kolibri-dispatch fabric-route agent-02 --required-capability implementation
python3 ops/kolibri-dispatch fabric-routes
```

Result:

- Live deployed Control Plane returned HTTP `404` for `/v1/fabric/route` and `/v1/fabric/routes` from this worker.
- This is a deploy/runtime contract blocker, because the checked-in source contains the route contracts but the live endpoint queried here does not expose them.

```bash
python3 ops/kolibri-dispatch status P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02
```

Result:

- State: `running`.
- Target node: `mesh-agent-02`.
- Lease owner: `mesh-agent-02:agent-host-mesh-agent-02`.
- Worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-02/worktrees/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02-attempt-1/repo`.
- This proves current safe-route execution on the live agent-02 mesh identity.

```bash
python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02
```

Result:

- State: `completed`.
- The task includes `cancel_requested_at=2026-07-02T02:58:05.437100+00:00`.
- Its result states the intended `mesh-agent-02` readiness probe was misrouted to `mesh-agent-24`, then cancelled to avoid concurrent wrong-node writes.
- Its exact result artifact is `/var/lib/kolibri-agent/logical-workers/mesh-agent-24/artifacts/P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02/P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02-attempt-1/result.json`.

```bash
python3 - <<'PY'
import json, urllib.request
url='http://10.99.0.2:9101/v1/tasks'
with urllib.request.urlopen(url, timeout=20) as r:
    data=json.load(r)
tasks=data.get('tasks', data if isinstance(data, list) else [])
terms=('hostvds','agent-02','mesh-agent-02','cancel')
rows=[t for t in tasks if any(term in json.dumps(t, ensure_ascii=False).lower() for term in terms)]
print(len(rows))
PY
```

Result:

- The filtered task scan found old `target_node=agent-02` tasks still queued with no lease.
- It also found the current safe-route task running on `mesh-agent-02`.

Final artifact checks:

```bash
test -f docs/agent/runs/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02/PLAN.md
test -f docs/agent/runs/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02/ACTIONS.md
test -f docs/agent/runs/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02/TESTS.md
test -f docs/agent/runs/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02/RESULT.md
test -f docs/agent/runs/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02/NEXT.md
git diff --check
```

Result:

- Required artifact files exist.
- Follow-up dispatcher envelope parses as JSON:
  - `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_REPAIR_HOSTVDS_AGENT_02_TARGETED_LEASE_AND_FABRIC_ROUTE_2026_07_02.json >/dev/null`
- `git diff --check` passed.
- Broad secret-word scan only matched safety-policy text such as `secrets`, `tokens`, and `private keys`.
- Narrow high-risk credential scan found no matches:

```bash
rg -n "(BEGIN [A-Z ]*PRIVATE KEY|github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9_]+|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})" docs/agent/runs/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02 docs/agent/dispatcher/envelopes/P0_REPAIR_HOSTVDS_AGENT_02_TARGETED_LEASE_AND_FABRIC_ROUTE_2026_07_02.json
```
