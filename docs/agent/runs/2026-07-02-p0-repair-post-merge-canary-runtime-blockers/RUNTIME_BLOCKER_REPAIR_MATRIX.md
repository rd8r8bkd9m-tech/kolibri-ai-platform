# Runtime Blocker Repair Matrix

Status: `partially_repaired_precisely_classified`

| ID | Source blocker | Repair/classification | Redacted evidence | Remaining next action |
| --- | --- | --- | --- | --- |
| `artifact-contract` | Source canary finalizer failed on missing `NEXT_REMOTE_TASKS.md`. | `repaired` | Source `result.json` error: `command failed with rc=1: test -f docs/agent/runs/2026-07-02-p0-post-merge-remote-canary-execution/NEXT_REMOTE_TASKS.md`; this branch now contains that file. | Rerun artifact file checks from this branch. |
| `B1` | Telegram gateway inactive/dead. | `classified_owner_approval_required` | `systemctl is-active kolibri-telegram-gateway.service` returned `inactive`; `systemctl show` returned `LoadState=loaded`, `ActiveState=inactive`, `SubState=dead`, `ExecMainPID=0`, `ExecStart=/usr/bin/python3 /usr/local/bin/kolibri-telegram-gateway --control-url http://10.99.0.10:9101`. | Owner-approved no-mutation preflight, then start/restart only existing `kolibri-telegram-gateway.service` if approved; verify no webhook/delete/send mutation. |
| `B2` | Live Fabric API route mismatch. | `classified_stale_or_incomplete_deploy` | `curl` returned HTTP `200` for `/health` and `/v1/health` on both `10.99.0.2:9101` and `10.99.0.10:9101`, but HTTP `404` for `/v1/fabric/health`, `/v1/fabric/routes`, `/v1/fleet/nodes`, and `/v1/models` on both listeners. Checked-in `ops/factory_control.py` contains these routes, so runtime is behind code or another listener is authoritative. | Deploy/restart existing Factory Control unit after preflight, or locate authoritative listener and update dispatcher URL. |
| `B3` | Factory-status freshness tests blocked by missing `httpx`. | `classified_environment_packaging_blocker` | `python3 -m pip show httpx` returned missing; `python3 -m pip install --user httpx` failed with `externally-managed-environment`. No repo dependency file was modified. | Use an approved venv/system-package repair path, then rerun `tests/test_factory_status.py` and `backend/tests/test_factory_status_fast_health.py`. |
| `B4` | GitHub PR queue metadata unavailable. | `classified_node_tooling_auth_blocker` | `command -v gh` returned no executable; `./ops/kolibri-dispatch doctor` reported `github_auth` error `[Errno 2] No such file or directory: 'gh'`. | Recheck PR metadata from a node with GitHub CLI/app auth, or install/configure `gh` through an approved node tooling task. |

No service restart was performed.

No Telegram Bot API state was mutated.

