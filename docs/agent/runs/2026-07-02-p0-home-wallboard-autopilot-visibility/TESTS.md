# Tests

Task id: `P0_HOME_WALLBOARD_AUTOPILOT_VISIBILITY_2026_07_02`

Status: `passed_with_visibility_blocker`

Lease owner: `mesh-agent-03/autonomous_engineer`

Verification commands:

```bash
hostname && uname -a && whoami
```

Result: ran on server `kolibri`, Linux x86_64, as `root`; not Mac.

```bash
systemctl is-active kolibri-factory-control.service kolibri-agent-host.service kolibri-mesh-control-bridge.service kolibri-telegram-gateway.service
```

Result: all four services returned `active`.

```bash
curl -fsS --max-time 5 http://10.99.0.10:9101/v1/health | jq '{status, data: .data}'
```

Result: HTTP 200; `status=completed`; Redis probe returned `PONG`.

```bash
curl -fsS --max-time 5 http://10.99.0.10:9101/v1/fleet/nodes | jq '{status, count: (.data.nodes|length)}'
```

Result: HTTP 200; 53 control-plane nodes.

```bash
python3 ops/home_wallboard_status_ru.py --timeout 10
```

Result: renderer returned Russian status; control plane showed 53 nodes, 47 online, 6 degraded/stale, 670 total tasks, 151 queued, and 7 running at probe time.

```bash
curl -fsS --max-time 5 http://127.0.0.1/api/factory/status | jq '{product, runtime, nodes, tasks}'
```

Result: HTTP 200; product `Колибри`; runtime `compatibility_gateway`; public status node/task totals are zero.

```bash
python3 -m pytest tests/test_home_wallboard_status_ru.py
```

Result: 4 passed.

```bash
python3 -m py_compile ops/home_wallboard_status_ru.py
```

Result: passed.

Broader related check:

```bash
python3 -m pytest tests/test_factory_status.py tests/test_home_wallboard_status_ru.py
```

Result: blocked during collection of `tests/test_factory_status.py` because the current Python environment does not have `httpx` installed. The new focused test file still passed independently.

Forbidden action checks:

- No live service restart/start/stop was run.
- No Telegram Bot API mutation was run.
- No secrets were printed.
