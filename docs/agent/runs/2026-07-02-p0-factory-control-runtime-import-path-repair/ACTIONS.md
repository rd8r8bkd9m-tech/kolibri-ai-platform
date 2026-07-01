# Actions

Remote agent: `Павел - Factory Control Runtime Packager`

Actions completed on server branch
`p0/factory-control-runtime-import-path-repair-2026-07-02`:

1. Updated `ops/factory_control.py` with robust ops-directory discovery for
   repo, systemd, and single-file launcher modes.
2. Updated `ops/systemd/kolibri-factory-control.service` to run the repo-owned
   `ops/factory_control.py` with explicit `KOLIBRI_REPO_ROOT`,
   `KOLIBRI_OPS_DIR`, and `WorkingDirectory`.
3. Added `scripts/preflight-factory-control-runtime.sh`.
4. Added `tests/test_factory_control_runtime_import_path.py`.
5. Committed remote branch head:
   `22daafe fix factory control runtime import path`.
6. Did not restart services, install runtime files, mutate Telegram, push to
   `main`, force push, or print secrets.

Thin-client dispatcher action:

- Added these exact run artifacts because the Control Plane wrapper failed on
  missing `PLAN.md` after the useful remote branch was produced.

