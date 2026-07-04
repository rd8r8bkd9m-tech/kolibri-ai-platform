# Import Path Repair Matrix

| Requirement | Implementation | Evidence | Risk | Next action |
| --- | --- | --- | --- | --- |
| Single-file launcher can import sibling ops modules | `factory_ops_import_paths()` searches current dir, explicit env vars, cwd `ops`, and known deploy ops paths | `tests/test_factory_control_runtime_import_path.py` reproduces copied launcher mode | Known deploy paths may differ by node | Verify on target node before rollout |
| Systemd should run repo-owned Factory Control | Unit uses `WorkingDirectory=/opt/kolibri-ai-platform`, `KOLIBRI_REPO_ROOT`, `KOLIBRI_OPS_DIR`, and `/usr/bin/python3 /opt/kolibri-ai-platform/ops/factory_control.py` | Unit contract test | `/opt/kolibri-ai-platform` may not be authoritative on every node | Confirm target repo path in deploy canary |
| Broken live deploy should be blocked before restart | `scripts/preflight-factory-control-runtime.sh` checks import path, unit contract, and route declarations | Preflight printed `factory_control_runtime_preflight=ok` on remote worktree | Preflight is repo-level, not yet run against live target path | Run preflight on target node before service restart |
| Fabric route surface is protected | Preflight checks required `/v1/*` and `/v1/fabric/*` route declarations | Focused tests passed | Live route exposure still requires deploy/restart | Run post-deploy canary after merge |

