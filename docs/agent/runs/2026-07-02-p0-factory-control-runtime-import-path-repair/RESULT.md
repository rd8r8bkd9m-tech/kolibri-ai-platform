# Result

Status: `failed_useful_branch_artifacts_relayed`

Task id: `P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_REPAIR_2026_07_02`

Control Plane status:

- State: `failed`.
- Error type: `runtime_error`.
- Error: missing exact `PLAN.md`.
- Result artifact:
  `/var/lib/kolibri-agent/artifacts/P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_REPAIR_2026_07_02/P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_REPAIR_2026_07_02-attempt-1/result.json`.

Useful remote result:

- Branch: `p0/factory-control-runtime-import-path-repair-2026-07-02`.
- Commit: `22daafe fix factory control runtime import path`.
- Changed files:
  - `ops/factory_control.py`
  - `ops/systemd/kolibri-factory-control.service`
  - `scripts/preflight-factory-control-runtime.sh`
  - `tests/test_factory_control_runtime_import_path.py`
- Focused tests passed.
- No live service restart or runtime file install was performed.

Risk:

- The systemd unit assumes the deployed repo path is
  `/opt/kolibri-ai-platform`. Nodes using another authoritative repo path must
  set `KOLIBRI_REPO_ROOT` and `KOLIBRI_OPS_DIR` consistently or adjust the unit
  before rollout.

Next exact task:

`P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_PR_RELEASE_GATE_2026_07_02`

