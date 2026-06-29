# Secondary Control Plane Watchdog

- Last checked (UTC): 2026-06-29T06:24:40Z
- Status: OK
- Control Plane health: reachable
- Redis: PONG
- Last successful check (UTC): 2026-06-29T06:24:40Z

## Heartbeat

Secondary Control Plane responded successfully on `/health`, `/v1/nodes`, and `/v1/tasks?summary=1&compact=1` at 2026-06-29T06:24:40Z.

- Queue: 64 queued, 0 active, 0 expired leases, 0 leases expiring soon
- Nodes: 35 total, 6 online/fresh, 29 stale, 3 draining
- Sample online nodes: `home`, `home-live`, `main`, `new`, `qjns`, `uiap`
- Sample stale nodes: `9fts`, `agent-01`, `agent-02`, `agent-03`, `agent-04`, `agent-05`, `agent-06`, `agent-07`
- Sample draining nodes: `home-live`, `qjns`, `uiap`
- Dead-letter active tasks observed on stale nodes: `TG-20260629003017-4711-up-telegram` (`9fts`) and `KOL-META-MIMO-ORCHESTRATOR-PRIMARY-20260629` (`primary-candidate`)
- Disk pressure: node `uiap` is online but reports `disk.free = 0` and remains draining

## Impact

No control-plane outage detected during this check. Scheduler backlog remains present, a large share of nodes are stale, and at least one online node is under disk pressure, but the secondary control plane is serving API traffic and Redis is healthy.

## Incident Handling

No GitHub issue opened or updated in this run because the control plane was reachable and Redis returned `PONG`.
