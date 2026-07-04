# Runtime Canary Report

Target:

- Node: `kolibri` / `primary-candidate`
- Endpoint: `http://10.99.0.10:9101`
- Service: `kolibri-factory-control.service`
- Runtime file: `/opt/kolibri-ai-platform/ops/factory_control.py`

Pre-deploy observations:

- `kolibri-factory-control.service` was active before deploy.
- Before restart, service status showed PID `3181870`, `Tasks: 3773`, memory `6.4G`, and CPU over one day.
- `/opt/kolibri-ai-platform` was not a Git checkout.
- Raw branch deployment was rejected because it would overwrite live registry/access-fabric runtime code.

Patch applied to live runtime:

- Bounded `ThreadingHTTPServer` admission with max workers and backlog.
- Structured lease `no_task` and `overloaded` response envelopes.
- Lease canary classifier helper.
- Bounded queue scan limit.
- Lock-gated, batched expired-lease reaper.
- Capacity controls surfaced in health/status responses.

Initial non-target probe:

- Endpoint: `http://10.99.0.2:9101`
- Result: health routes passed, but 250/250 lease canary requests returned HTTP 204.
- Classification: not the local target endpoint for this deploy; records remaining main-endpoint legacy behavior.

First local canary:

- Endpoint: `http://10.99.0.10:9101`
- Requests: 250
- Concurrency: 25
- HTTP 200 responses: 215
- Client timeouts: 35
- Lease 5xx: 0
- Leased tasks: 0
- Residual blocker: unbounded expired-lease reaper still executed on lease path.

Final local canary:

```json
{
  "base": "http://10.99.0.10:9101",
  "lease_canary": {
    "concurrency": 25,
    "elapsed_ms_max": 835.82,
    "elapsed_ms_min": 9.76,
    "elapsed_ms_p50": 89.64,
    "elapsed_ms_p95": 124.06,
    "http_status_counts": {
      "200": 250
    },
    "lease_5xx_count": 0,
    "leased_task_count": 0,
    "non_200_count": 0,
    "reason_counts": {
      "queue_empty": 250
    },
    "requests": 250
  },
  "routes": {
    "/health": {"http_status": 200, "status": "completed"},
    "/v1/health": {"http_status": 200, "status": "completed"},
    "/v1/fabric/health": {"http_status": 200, "status": "ok"},
    "/v1/fabric/routes": {"http_status": 200, "status": "ok"},
    "/v1/fleet/nodes": {"http_status": 200, "status": "completed"},
    "/v1/models": {"http_status": 200, "status": "completed"}
  }
}
```

Verdict:

- Runtime canary passed on local healthy node.
- No full worker wave was requeued.
- No canary task was leased.
- No rollback was required.

