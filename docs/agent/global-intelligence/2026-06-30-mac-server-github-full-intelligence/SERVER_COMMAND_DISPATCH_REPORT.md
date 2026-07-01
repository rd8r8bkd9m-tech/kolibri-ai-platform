# Server command and dispatch report

## Scope

Requested server set: 20 nodes.

Nodes:

`home`, `main`, `uiap`, `qjns`, `9fts`, `new`, `primary-candidate`, `agent-01`, `agent-02`, `agent-03`, `agent-04`, `agent-05`, `agent-06`, `agent-07`, `agent-08`, `agent-09`, `highload`, `paris`, `reserve242`, `server-kfrm`.

## Direct SSH from Mac

- reachable: 2 of 20.
- timed out/unreachable from Mac route: 18 of 20.

Reachable:

- `main` via configured root route.
- `primary-candidate` via configured `kolibri-primary-codex` route.

Most other aliases timed out through the configured jump path, likely firewall/VPN/jump routing rather than proof that the nodes are down. Control Plane node cards show the nodes as fresh/known.

## Main server mini-scan

- host: `kolibri-main-api`.
- OS: Linux Ubuntu kernel 6.8.0-35.
- user: root.
- uptime: about 2 weeks.
- disk root: about 7.4 GB free, 60% used.
- memory available: about 757 MB.
- Control Plane health: OK, Redis PONG.
- runtime repo: `/var/lib/kolibri-agent/runtime-repo`.
- repo branch: `main`.
- repo head: `6d0317c`.
- dirty: `ops/factory_control.py`, `ops/mesh_control_bridge.py`, backup file.
- active services include factory control, agent host, mesh bridge, frontend dev and AI service.
- GitHub HTTPS fetch/ls-remote failed non-interactively because credentials were unavailable.

## Primary-candidate mini-scan

- host: `kolibri`.
- OS: Linux Ubuntu kernel 6.8.0-36.
- user: root.
- uptime: about 6 days.
- disk root: about 65 GB free, 31% used.
- memory available: about 10 GB.
- Control Plane health: OK, Redis PONG.
- runtime repo: `/var/lib/kolibri-agent/runtime-repo`.
- repo branch: `codex/version-mesh-control-bridge`.
- repo head: `ad947ba`.
- behind `origin/main`: about 3 commits.
- dirty product files: backend providers, infra network API/organism, agent host, factory control, Telegram gateway, runtime tests.
- services include remote control, agent host instances, docs portal, factory control standby.
- GitHub HTTPS fetch/ls-remote failed non-interactively because credentials were unavailable.

## Dispatch observations

- Control Plane health is OK from server side.
- `/v1/tasks` returned a large/truncated queue in previous scan.
- agent messages are active.
- direct task result retrieval from all nodes is limited by SSH reachability and CP artifact path availability.

## Blockers

- `control-plane` itself is reachable from live server side, but direct Mac routes to most nodes are blocked.
- server GitHub auth must be fixed without leaking tokens.
- runner must enforce artifact paths and no-push/no-product-modification constraints.
