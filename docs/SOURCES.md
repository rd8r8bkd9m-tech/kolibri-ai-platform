# Architecture Sources

Last updated: 2026-07-03

This catalog records the source files used by the Kolibri AI Control Center Home/NOC surface. It is intentionally architecture-focused and excludes secrets, live tokens, private logs, and billing/provider lifecycle details.

## Control Plane Runtime

| Source | Purpose |
| --- | --- |
| `ops/factory_control.py` | Factory Control Plane runtime, node registry, queue, tasks, leases, result states, Fabric relay routes, and runner block states. |
| `backend/factory_status.py` | Backend read model for `/api/factory/status`; normalizes Control Plane health, nodes, tasks, queue pressure, topology, Telegram HA status, runner/auth blocks, and owner attention. |
| `backend/main.py` | FastAPI application exposing `/api/factory/status` and fallback degraded status when Control Plane API is unreachable. |
| `ops/agent_host.py` | Agent runner behavior, required artifact gating, permission packs, runner auth failure reporting, and result finalization. |

## Home/NOC Frontend

| Source | Purpose |
| --- | --- |
| `frontend/src/App.jsx` | Kolibri AI Control Center shell and Server NOC Home monitor. Defaults Home to NOC, renders aggregate topology, search, pagination, active work, repairs, runner/auth blocks, Telegram HA, and owner attention. |
| `frontend/src/App.css` | Dense operational NOC layout, responsive KPI grids, aggregate topology rows, drilldown search table, pagination, and mobile constraints. |
| `frontend/tests/mobile_layout_guard.mjs` | Existing mobile layout guard for frontend rendering checks. |

## Product And Operations Contracts

| Source | Purpose |
| --- | --- |
| `docs/product/telegram-command-center/2026-07-01/COMMAND_CENTER_SPEC.md` | Command Center contract covering task board, fleet, agents, owner auth boundaries, safe Telegram behavior, and non-goals. |
| `docs/agent/AGENT_RUNNER_CONTRACT.md` | Agent runner artifact and permission discipline. |
| `tests/test_factory_status.py` | NOC read-model and frontend contract assertions for Control Plane status and Home rendering strings. |
| `tests/test_agent_host_runner_contract.py` | Runner auth, required artifact, permission, and blocked-result contract tests. |
| `tests/test_telegram_failover_guard.py` | Telegram HA/failover guard contracts. |
| `tests/test_telegram_gateway.py` | Telegram gateway state, owner command, task formatting, and no-secret behavior. |

## Current NOC Read Model

The Home monitor uses `/api/factory/status` and expects these major fields:

- `control_plane`: health, Redis/queue backend, degraded fallback reason.
- `node_freshness`: fresh, degraded, stale, online, offline, total.
- `queue_pressure`: normal/elevated/high/critical queue status.
- `active_tasks`, `active_repairs`, `runner_auth_blocks`: capped read lists with total counts.
- `telegram_ha`: primary, standby, promotion, and aggregate HA status.
- `owner_attention`: exact owner-facing attention counters.
- `topology`: aggregate hierarchy for `global -> region -> provider -> cluster -> cell -> node -> agent -> task`.

The frontend must not render all nodes at the global root for large fleets. It must drill down through aggregate topology and use search plus pagination for node-level rows.
