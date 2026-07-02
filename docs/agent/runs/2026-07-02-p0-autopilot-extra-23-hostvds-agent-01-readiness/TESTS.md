# Tests

Verification commands run:

```bash
git diff --check
```

Result: passed.

```bash
python3 ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02.json
```

Result: Control Plane accepted the task at `2026-07-02T02:56:53Z`.

```bash
python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02
```

Result at `2026-07-02T03:02:59Z`:

- `state`: `running`
- `target_node`: `mesh-agent-01`
- `allowed_nodes`: `["mesh-agent-01"]`
- `worktree`: `/var/lib/kolibri-agent/logical-workers/mesh-agent-23/.../repo`
- `log_paths`: `/var/lib/kolibri-agent/logical-workers/mesh-agent-23/artifacts/...`
- `result_reference`: `null`

```bash
python3 - <<'PY'
import urllib.request
for path in ["/health", "/v1/health"]:
    with urllib.request.urlopen("http://10.99.0.2:9101" + path, timeout=10) as r:
        print(path, r.status)
PY
```

Result:

- `/health`: `200`
- `/v1/health`: `200`
- response status: `ok`
- queue backend: `redis`

```bash
python3 ops/kolibri-dispatch fabric-routes || true
```

Result: `/v1/fabric/routes` returned HTTP `404`; this helper route is unavailable in the current deployed Control Plane.

```bash
python3 ops/kolibri-dispatch nodes
```

Filtered result:

- `mesh-agent-01`: `health=online`, `fresh=true`, `active_task=null`, capabilities include `runner:codex` and `runner:mimo`.
- `mesh-agent-23`: `health=online`, `fresh=true`, `active_task=P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02`.
- stale metadata alias `agent-01`: `health=stale`, heartbeat `2026-06-30T11:56:41Z`.

Secret check:

- No secrets, tokens, environment values, private keys, or raw credential values were printed into these artifacts.
