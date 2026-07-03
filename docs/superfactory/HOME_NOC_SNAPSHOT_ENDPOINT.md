# Home NOC Snapshot Endpoint

## Overview

The `/api/snapshot` endpoint provides a bounded fleet summary for the Home monitor
acting as a server-side NOC (Network Operations Center). It returns real fleet and
task data sourced from the Kolibri control plane.

## Endpoint

```
GET /api/snapshot
```

### Response schema

| Field | Type | Description |
|---|---|---|
| `snapshot` | `bool` | Always `true` |
| `generated_at` | `str` | ISO-8601 timestamp |
| `source` | `str` | Always `"control-plane"` |
| `status` | `str` | `"online"` or `"degraded"` |
| `total_nodes` | `int` | Total registered nodes |
| `online_nodes` | `int` | Nodes with `"online"` freshness |
| `fresh_nodes` | `int` | Nodes with heartbeat < 30s |
| `degraded_nodes` | `int` | Nodes with heartbeat 30-90s |
| `stale_nodes` | `int` | Nodes with heartbeat > 90s or missing |
| `node_freshness` | `dict` | Counters for fresh/degraded/stale/online/total |
| `free_ram_gb` | `float` | Aggregate free RAM |
| `total_ram_gb` | `float` | Aggregate total RAM |
| `avg_cpu_percent` | `float` | Average CPU across nodes |
| `queue_size` | `int` | Active tasks (queued + leased + running) |
| `task_states` | `dict` | Task count per state |
| `task_queue` | `list` | Active task entries (bounded) |
| `nodes` | `list` | Node cards (bounded by `FLEET_SNAPSHOT_MAX_NODES`) |

### Degraded fallback

When the control plane is unreachable, the endpoint returns HTTP 503 with the same
schema but `total_nodes: 0`, `status: "degraded"`, and `error` set to the exception
message.

## Runtime backup

1. The existing `/api/factory/status` endpoint is the primary fleet data source
   used by the frontend. It shares the same control plane upstream.
2. If `/api/snapshot` fails, `/api/factory/status` and `/cluster/status` remain
   available as alternative fleet data sources.
3. The frontend polls `/api/factory/status` every 15 seconds and renders the
   ClusterView component independently of the snapshot endpoint.

## Rollback

To remove the snapshot endpoint without affecting the rest of the system:

1. Remove the `/api/snapshot` route from `backend/main.py`.
2. Remove `fetch_fleet_summary_snapshot` from the import line.
3. Remove `build_fleet_summary_snapshot`, `fetch_fleet_summary_snapshot`, and
   `SNAPSHOT_MAX_NODES` from `backend/factory_status.py`.
4. Remove snapshot tests from `tests/test_factory_status.py`.

No other endpoints depend on the snapshot code. The rollback is self-contained.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `FLEET_SNAPSHOT_MAX_NODES` | `20` | Maximum nodes returned in snapshot |
| `KOLIBRI_FACTORY_CONTROL_URL` | `http://control.kolibri.internal:9101` | Control plane base URL |

## Security

- The endpoint does not print or expose secrets, tokens, or credentials.
- Control plane URL and Redis connection details are not returned in the snapshot
  response (unlike `/api/factory/status` which includes `control_plane.url`).
- Rate limiting is inherited from the FastAPI server configuration.
