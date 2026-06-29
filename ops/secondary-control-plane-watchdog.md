# Secondary Control Plane Watchdog

- Last checked (UTC): 2026-06-29T07:14:25Z
- Status: OK
- Control Plane health: reachable
- Redis: PONG
- Last successful check (UTC): 2026-06-29T07:14:25Z

## Heartbeat

Secondary Control Plane responded successfully on `/health`, `/v1/nodes`, and `/v1/tasks?summary=1&compact=1` at 2026-06-29T07:14:25Z.

- Queue: 65 queued, 0 active, 0 expired leases, 0 leases expiring soon
- Nodes: 42 registered, 25 online/fresh, 17 stale, 3 draining
- Fresh non-draining nodes: 22
- Sample online nodes: `home-live`, `main`, `mesh-9fts`, `mesh-agent-01`, `mesh-agent-02`
- Sample stale nodes: `9fts`, `agent-01`, `agent-02`, `agent-03`, `agent-04`, `agent-05`, `agent-06`, `agent-07`, `agent-08`, `agent-09`
- Sample draining nodes: `home-live`, `qjns`, `uiap`
- Dead-letter active tasks observed on stale nodes: `TG-20260629003017-4711-up-telegram` (`9fts`) and `KOL-META-MIMO-ORCHESTRATOR-PRIMARY-20260629` (`primary-candidate`)
- Disk pressure: node `uiap` is online but reports `disk.free = 0` and remains draining
- Newest queued tasks sampled: `TGCHAT-20260629070132-4727-task`, `TGCHAT-20260629062652-4724-task`, `KOL-P0-APP-VERIFY-REVIEW-20260629`, `TGCHAT-20260629052635-4722-task`, `TGCHAT-20260629051708-4720-task`

## Impact

No control-plane outage is confirmed in the final verification window. Scheduler backlog remains present, a large share of nodes are stale, and at least one online node is under disk pressure, but the secondary control plane is serving API traffic and Redis is healthy.

## Incident Handling

No GitHub issue opened or updated in this run because the control plane was reachable and Redis returned `PONG`.
