# Runtime Blockers

Status: `blocked_runtime_canary`

Blockers:

| ID | Surface | Exact evidence | Impact | Next action |
| --- | --- | --- | --- | --- |
| `B1` | Telegram runtime | `systemctl is-active kolibri-telegram-gateway.service` returned `inactive`; `systemctl show` reported `ActiveState=inactive`, `SubState=dead`, `ExecMainPID=0`. | Live Telegram runtime cannot be classified as post-merge healthy. | Run a no-mutation Telegram gateway restoration/diagnostic task on a server node, then rerun this canary. |
| `B2` | Fabric API live route | `curl --noproxy '*' -fsS --max-time 2 http://10.99.0.10:9101/v1/fabric/health` returned HTTP `404`; `/v1/fleet` and `/v1/status` also returned HTTP `404`. | Fabric API contract tests pass, but the live listener at `10.99.0.10:9101` does not expose the expected `/v1` routes. | Identify the authoritative live Fabric API listener or repair route mounting, then rerun read-only `/v1` health/status/artifact probes. |
| `B3` | Control Plane freshness tests | `tests/test_factory_status.py` and `backend/tests/test_factory_status_fast_health.py` failed collection with `ModuleNotFoundError: No module named 'httpx'`. | Full factory-status freshness test coverage cannot run in this node environment. | Install/sync the server test dependency environment without changing repo code, then rerun the factory-status tests. |
| `B4` | GitHub PR queue metadata | `command -v gh` produced no executable path; only git pull refs were available. | PR refs are visible, but open/draft/mergeability/check-state classification is blocked. | Run a GitHub metadata recheck from a node with `gh` auth or the GitHub connector before any owner merge decision. |

Non-blocking evidence:

- Factory Control `/health` returned `status=ok`, `redis=PONG`, `spool_count=0`, and `spool_replayed=0`.
- `kolibri-agent-host.service`, `kolibri-factory-control.service`, and `kolibri-mesh-control-bridge.service` are active.
- Focused contract canary suite passed: `89 passed in 40.05s`.

