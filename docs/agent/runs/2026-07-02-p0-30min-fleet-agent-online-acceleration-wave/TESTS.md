# Tests

Read-only verification commands:

```bash
hostname
date -u +%Y-%m-%dT%H:%M:%SZ
git rev-parse --show-toplevel
git rev-parse --abbrev-ref HEAD
```

Result:

- Host: `kolibri`
- Timestamp checked: `2026-07-02T00:18:21Z`
- Worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-02/worktrees/P0_30MIN_FLEET_AGENT_ONLINE_ACCELERATION_WAVE_2026_07_02/P0_30MIN_FLEET_AGENT_ONLINE_ACCELERATION_WAVE_2026_07_02-attempt-1/repo`
- Branch: `agent/P0_30MIN_FLEET_AGENT_ONLINE_ACCELERATION_WAVE_2026_07_02/generic`

Endpoint reachability checks:

```bash
python3 - <<'PY'
import json, urllib.request
for base in ["http://10.99.0.10:9101", "http://10.99.0.2:9101"]:
    for ep in ["/health", "/v1/nodes", "/v1/tasks", "/v1/fabric/routes", "/v1/fleet/nodes"]:
        req = urllib.request.Request(base + ep, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            print(base, ep, r.status, len(r.read()))
PY
```

Observed sanitized result:

| Endpoint | Result |
|---|---|
| `10.99.0.10 /health` | HTTP 200 |
| `10.99.0.10 /v1/nodes` | HTTP 200 |
| `10.99.0.10 /v1/tasks` | HTTP 200 |
| `10.99.0.10 /v1/fabric/routes` | HTTP 200 |
| `10.99.0.10 /v1/fleet/nodes` | HTTP 200 |
| `10.99.0.2 /health` | HTTP 200 |
| `10.99.0.2 /v1/nodes` | HTTP 200 after a transient first-loop timeout |
| `10.99.0.2 /v1/tasks` | HTTP 200 |
| `10.99.0.2 /v1/fabric/routes` | HTTP error |
| `10.99.0.2 /v1/fleet/nodes` | HTTP error |

Notes:

- The first loop parser undercounted `/v1/fleet/nodes` because that endpoint wraps node data under `data`.
- Capacity classification therefore uses `/v1/nodes`; Fabric repair planning uses `/v1/fleet/nodes` and `/v1/fabric/routes`.
- No command printed environment variables, tokens, credentials, private keys, or secret-bearing configuration.

