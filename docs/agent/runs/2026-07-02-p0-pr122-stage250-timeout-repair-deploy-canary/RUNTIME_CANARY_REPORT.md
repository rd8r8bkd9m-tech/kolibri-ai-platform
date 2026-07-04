# Runtime Canary Report

Status: `passed_runtime_canary`

Task: `REBROADCAST_P0_PR122_STAGE250_TIMEOUT_REPAIR_DEPLOY_AND_CANARY_2026_07_02-DELIVERABLE-RETRY`

Control Plane endpoint: `http://10.99.0.2:9101`

Execution node:

- Control Plane lease owner: `main:agent-host-main`
- Hostname: `kolibri-main-api`
- Node health during run: `online`, fresh heartbeat
- No qjns/uiap targeting was used.

PR #125 evidence:

- PR URL: `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/125`
- Head SHA: `f152e74711ad4f08b71551502ed273885cf4551d`
- Merge SHA: `0bda96ca5bb62c375b26bae902fa01558b119e29`
- Head commit title: `control-plane: bound lease overload admission backlog`

Live runtime markers:

| Marker | Present |
| --- | --- |
| `BoundedThreadingHTTPServer` | yes |
| `LEASE_QUEUE_SCAN_LIMIT` | yes |
| `maybe_requeue_expired_leases` | yes |
| `lease_next_task` | yes |
| `FACTORY_MAX_HTTP_WORKERS` | yes |

Bounded stage canary:

Synthetic request body used `node_id=pr125-stage250-canary-no-claim`, `agent_id=pr125-stage250-canary-no-claim`, `capabilities=["stage250_synthetic_no_match"]`, `permissions=[]`, and `runners={}`. This was intended to exercise the lease fast path without claiming queued work.

| Stage | Requests | HTTP result | Claimed tasks | Errors | 5xx | p50 ms | p95 ms | max ms | wall ms |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 20 | `204 x20` | 0 | 0 | 0 | 273.66 | 292.95 | 302.45 | 347.52 |
| 50 | 50 | `204 x50` | 0 | 0 | 0 | 523.01 | 598.78 | 625.82 | 825.82 |
| 100 | 100 | `204 x100` | 0 | 0 | 0 | 706.15 | 1056.28 | 1101.37 | 1453.19 |
| 250 | 250 | `204 x250` | 0 | 0 | 0 | 2272.77 | 3043.31 | 3154.37 | 4704.15 |

Pre-canary health:

| Route | HTTP | ms |
| --- | ---: | ---: |
| `/health` | 200 | 359.92 |
| `/v1/health` | 200 | 64.13 |
| `/v1/fabric/health` | 200 | 75.37 |
| `/v1/tasks?limit=1` | 200 | 402.38 |

Post-canary health:

| Route | HTTP | ms |
| --- | ---: | ---: |
| `/health` | 200 | 379.75 |
| `/v1/health` | 200 | 88.00 |
| `/v1/fabric/health` | 200 | 65.17 |
| `/v1/tasks?limit=1` | 200 | 375.01 |

Required route matrix after canary:

| Route | HTTP | ms | Bytes |
| --- | ---: | ---: | ---: |
| `/health` | 200 | 1207.30 | 113 |
| `/v1/health` | 200 | 193.96 | 113 |
| `/v1/fabric/health` | 200 | 110.99 | 231 |
| `/v1/fabric/routes` | 200 | 3143.34 | 25279 |
| `/v1/fleet/nodes` | 200 | 2782.22 | 28201 |
| `/v1/models` | 200 | 5.19 | 442 |

Post-canary service/resource state:

- `kolibri-factory-control.service`: `active/running`
- Active since: `2026-07-04 05:18:57 UTC`
- Main PID: `871480`
- Threads after canary: `15` by `ps`, `8` by `systemctl status` sample
- File descriptors after canary: `28`
- `LimitNOFILE`: `524288`
- `TasksMax`: `2287`
- `NRestarts`: `0` after the active runtime entered
- Journal scan found no `BrokenPipe`, `Too many open files`, `Traceback`, `ERROR`, `Errno 24`, or explicit ` 500 ` lines in the canary window.

Canary decision:

The bounded stage-250 canary passed. Rollback was not executed. Do not launch a full worker wave from this result; broaden only through a separate owner-approved staged rollout.

