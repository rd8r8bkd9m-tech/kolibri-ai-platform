# Actions

Task id: `P0_HOME_WALLBOARD_AUTOPILOT_VISIBILITY_2026_07_02`

Status: `implemented_with_visibility_blocker`

Lease owner: `mesh-agent-03/autonomous_engineer`

Actions performed:

- Confirmed execution host is server `kolibri`, Linux x86_64, user `root`; this was not executed on Mac.
- Added `ops/home_wallboard_status_ru.py`, a read-only Russian terminal status renderer for Home or fallback tmux.
- Added unit tests in `tests/test_home_wallboard_status_ru.py`.
- Probed systemd service state with read-only `systemctl is-active/show`.
- Probed control-plane routes with read-only HTTP `GET` requests.
- Probed public status path with read-only HTTP `GET`.
- Created exact run artifacts under this directory.

Current verified service state:

| Service | State |
| --- | --- |
| `kolibri-factory-control.service` | `active/running` |
| `kolibri-agent-host.service` | `active/running` |
| `kolibri-mesh-control-bridge.service` | `active/running` |
| `kolibri-telegram-gateway.service` | `active/running` |

Verified status paths:

| Path | Result |
| --- | --- |
| `http://10.99.0.10:9101/health` | HTTP 200 |
| `http://10.99.0.10:9101/v1/health` | HTTP 200, Redis `PONG` |
| `http://10.99.0.10:9101/v1/fleet/nodes` | HTTP 200, 53 nodes in control-plane envelope |
| `http://10.99.0.10:9101/v1/tasks?limit=25` | HTTP 200, renderer observed 670 total tasks, 151 queued, 7 running |
| `http://127.0.0.1/api/factory/status` | HTTP 200, Russian product `Колибри`, `compatibility_gateway` payload |
| `http://127.0.0.1/cluster/status` | HTTP 200, frontend HTML fallback |

Visibility blocker:

- The public status path is reachable, but `http://127.0.0.1/api/factory/status` currently reports zero public node/task totals while the control-plane route reports live data. That means the owner-visible public status path cannot yet be treated as complete autopilot visibility unless the terminal renderer is deployed as the accepted fallback surface.

Attach/view command for fallback Agent Host:

```bash
python3 ops/home_wallboard_status_ru.py
```

Suggested tmux command after owner approval on Home or fallback host:

```bash
tmux new-session -d -s kolibri-factory-screen 'watch -n 10 python3 /opt/kolibri-ai-platform/ops/home_wallboard_status_ru.py'
tmux attach -t kolibri-factory-screen
```

This command is read-only. It should only be run after confirming the target path and operator approval for creating or replacing the display session.
