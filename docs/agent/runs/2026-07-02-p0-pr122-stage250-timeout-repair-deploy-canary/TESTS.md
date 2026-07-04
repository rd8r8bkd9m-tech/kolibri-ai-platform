# Tests

Runtime deploy checks:

```bash
python3 -m py_compile /opt/kolibri-ai-platform/ops/factory_control.py
scripts/preflight-factory-control-runtime.sh /opt/kolibri-ai-platform
systemctl restart kolibri-factory-control.service
systemctl is-active kolibri-factory-control.service
```

Results:

- `python3 -m py_compile /opt/kolibri-ai-platform/ops/factory_control.py`: passed.
- `scripts/preflight-factory-control-runtime.sh /opt/kolibri-ai-platform`: passed with `factory_control_runtime_preflight=ok`.
- `systemctl restart kolibri-factory-control.service`: passed.
- `systemctl is-active kolibri-factory-control.service`: `active`.

Route matrix after final restart:

| Route | HTTP | Status | Latency |
| --- | ---: | --- | ---: |
| `/health` | 200 | `completed` | 42.17 ms |
| `/v1/health` | 200 | `completed` | 2.01 ms |
| `/v1/fabric/health` | 200 | `ok` | 1.57 ms |
| `/v1/fabric/routes` | 200 | `ok` | 34.39 ms |
| `/v1/fleet/nodes` | 200 | `completed` | 34.39 ms |
| `/v1/models` | 200 | `completed` | 2.01 ms |

Capacity controls observed from `/v1/health`:

```json
{
  "http_request_backlog": 1024,
  "lease_queue_scan_limit": 100,
  "lease_reaper_batch_limit": 250,
  "lease_reaper_interval": 5.0,
  "max_http_workers": 64
}
```

Stage-250 lease canary:

- Endpoint: `http://10.99.0.10:9101/v1/tasks/lease`
- Requests: 250
- Concurrency: 25
- Payload capability: `stage250_runtime_canary_no_matching_task`
- HTTP status counts: `{"200": 250}`
- Reason counts: `{"queue_empty": 250}`
- Lease 5xx count: `0`
- Non-200 count: `0`
- Leased task count: `0`
- Latency min/p50/p95/max: `9.76 ms / 89.64 ms / 124.06 ms / 835.82 ms`

Repository checks:

```bash
pytest -q tests/test_factory_capacity_controls.py
git diff --check
test -s docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/PLAN.md
test -s docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/ACTIONS.md
test -s docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/TESTS.md
test -s docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/RESULT.md
test -s docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/NEXT.md
test -s docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/RUNTIME_CANARY_REPORT.md
test -s docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/ROLLBACK_RECORD.md
```

