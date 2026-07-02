# PR Queue Matrix

Snapshot time: 2026-07-02 UTC.

| PR | Branch | State | Draft | Mergeable | Classification | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| #83 | `p0/agent-host-runner-contract-hardening-2026-06-30` | merged | no | n/a | prior runner contract release gate landed | no action |
| #85 | `p0/api-first-full-control-fabric-2026-07-01` | merged | no | n/a | prior API-first Fabric release gate landed | no action |
| #88 | `codex/factory-dispatcher-ledger-2026-07-01` | merged | no | n/a | prior dispatcher ledger landed | no action |
| #89 | `p0/telegram-superfactory-bot-miniapp-2026-07-01` | merged | no | n/a | prior Telegram Superfactory landed; runtime receiver cutover still needs operational gate before live enablement | keep receiver gate separate |
| #90 | `p0/telegram-miniapp-owner-auth-contract-2026-07-01` | open | yes | yes | repair PR; dependency/test-environment blocker remains documented | repair/verify before merge |
| #91 | `p0/mimo-runner-output-auth-contract-repair-2026-07-01` | merged | no | n/a | prior MIMO runner classification landed | run post-merge canary before broad MIMO fanout |
| #92 | `p0/fleet-role-capability-inventory-2026-07-01` | merged | no | n/a | prior fleet inventory landed | no action |
| #96 | `p0/agent-host-readonly-permission-pack-runtime-gate-2026-07-01` | merged | no | n/a | prior read-only permission gate landed | use as baseline for runner/fleet PRs |
| #97 | `p0/control-plane-node-health-freshness-gate-2026-07-01` | merged | no | n/a | prior node freshness gate landed | use as baseline for fleet freshness PRs |
| #105 | `agent/P0_FLEET_ROUTE_FRESHNESS_GATE_2026_07_02/generic` | open | yes | yes | route freshness code PR; repair branch exists but is empty | needs CI/check evidence and focused review |
| #106 | `agent/P0_30MIN_12AGENT_05B_RUNNER_CONTRACT_STEWARD_FALLBACK_2026_07_02/generic` | open | yes | yes | runner contract follow-up code PR | review after #112 or combine strategy decision |
| #107 | `agent/P0_30MIN_MESH_AGENT_01_RELEASE_QUEUE_ACCELERATOR_2026_07_02/generic` | open | yes | yes | release queue accelerator code PR | review after runtime import/factory-control stability |
| #108 | `agent/P0_30MIN_MESH_AGENT_02_FLEET_ONLINE_ACCELERATOR_2026_07_02/generic` | open | yes | yes | fleet online/freshness accelerator code PR | review after #105/#110 ordering decision |
| #109 | `agent/P0_FACTORY_STATUS_PROXY_504_CANARY_2026_07_02/generic` | open | yes | yes | factory status 504 repair code PR | high-priority repair candidate |
| #110 | `agent/P0_PRIMARY_NODE_HEARTBEAT_REPAIR_READONLY_2026_07_02/generic` | open | yes | yes | heartbeat read-only repair code PR | review with #105/#108 for `ops/factory_control.py` overlap |
| #111 | `agent/P0_QUEUE_LEASE_DEBT_AUDIT_AND_REQUEUE_POLICY_2026_07_02/generic` | open | yes | yes | queue lease/requeue policy code PR | review after core runtime/fleet repairs |
| #112 | `agent/P0_RUNNER_TIMEBOX_AND_MAX_INFLIGHT_CONTRACT_REPAIR_2026_07_02/generic` | open | yes | yes | runner timebox/max-inflight code PR | high-priority runner repair candidate |
| #113 | `p0/factory-control-runtime-import-path-repair-2026-07-02` | open | yes | yes | factory-control runtime import repair code PR | first repair candidate |

Status note: commit combined-status queries returned empty legacy status contexts for active heads. Fresh GitHub Actions check conclusions need `gh` or another check-run-capable API path.
