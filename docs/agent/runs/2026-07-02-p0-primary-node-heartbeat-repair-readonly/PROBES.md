# Probes

Probe time window: `2026-07-02T02:27:00Z` to `2026-07-02T02:28:27Z`.

Runtime:

- `hostname`: `kolibri`
- `uname`: Linux `6.8.0-36-generic` x86_64
- `whoami`: `root`
- Branch: `agent/P0_PRIMARY_NODE_HEARTBEAT_REPAIR_READONLY_2026_07_02/generic`
- HEAD: `f7ac32c70406432a52752ca45d87e35d9f1facd3`

Factory Control:

- `kolibri-factory-control.service`: `active/running`
- PID: `3588876`
- Unit entrypoint: `/usr/bin/python3 /opt/kolibri-ai-platform/ops/factory_control.py`
- Listener: `10.99.0.10:9101`
- Loopback probe: `127.0.0.1:9101` refused connection

API route probes:

| Route | HTTP | Result |
| --- | ---: | --- |
| `/v1/health` | 200 | Redis `PONG`, Fabric API version `2026-07-01` |
| `/v1/fabric/health` | 200 | `status=ok`, primary management path `protected_fabric_api` |
| `/v1/nodes` | 200 | 53 nodes: 27 fresh, 1 degraded, 25 stale |
| `/v1/fleet/route?target_node=primary-candidate` | 200 | live route returned direct route before local fix |
| `/v1/fleet/route?target_node=primary-candidate&required_capability=generic_implementation` | 200 | live route returned direct route before local fix |

Heartbeat split evidence:

| Surface | State at probe |
| --- | --- |
| `primary-candidate` node heartbeat | `heartbeat_at=2026-07-02T02:27:05.482718+00:00`, `heartbeat_age_seconds=81`, `freshness=degraded`, `health=degraded`, `reported_health=online` |
| Active primary-owned task heartbeat | task `P0_30MIN_12AGENT_05B_RUNNER_CONTRACT_STEWARD_FALLBACK_2026_07_02`, `state=running`, `lease_owner=primary-candidate:agent-host-primary`, `heartbeat_at=2026-07-02T02:28:23.874857+00:00`, task heartbeat age 3 seconds |
| This task heartbeat | task `P0_PRIMARY_NODE_HEARTBEAT_REPAIR_READONLY_2026_07_02`, `state=running`, `lease_owner=mesh-agent-12:agent-host-mesh-agent-12`, `heartbeat_at=2026-07-02T02:28:21.337807+00:00`, task heartbeat age 5 seconds |

Sanitized journal evidence:

```text
2026-07-02T02:27:05.485044+00:00 "POST /v1/nodes/primary-candidate/heartbeat HTTP/1.1" 200 -
2026-07-02T02:27:05.496068+00:00 "POST /v1/tasks/P0_30MIN_12AGENT_05B_RUNNER_CONTRACT_STEWARD_FALLBACK_2026_07_02/heartbeat HTTP/1.1" 200 -
2026-07-02T02:27:11.508060+00:00 "POST /v1/tasks/P0_30MIN_12AGENT_05B_RUNNER_CONTRACT_STEWARD_FALLBACK_2026_07_02/heartbeat HTTP/1.1" 200 -
2026-07-02T02:27:17.518565+00:00 "POST /v1/tasks/P0_30MIN_12AGENT_05B_RUNNER_CONTRACT_STEWARD_FALLBACK_2026_07_02/heartbeat HTTP/1.1" 200 -
2026-07-02T02:28:23.875855+00:00 "POST /v1/tasks/P0_30MIN_12AGENT_05B_RUNNER_CONTRACT_STEWARD_FALLBACK_2026_07_02/heartbeat HTTP/1.1" 200 -
```

Classification:

- Task heartbeat path is working for a primary-owned task.
- Node heartbeat path for `primary-candidate` stopped refreshing after
  `2026-07-02T02:27:05.482718+00:00` during this probe window.
- Live route selection was still treating `primary-candidate` as directly
  routable because `fabric_route()` used raw registered node records rather
  than the freshness-classified records used by `/v1/nodes`.

