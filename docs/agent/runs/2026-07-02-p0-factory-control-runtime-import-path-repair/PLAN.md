# Plan

Task id: `P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_REPAIR_2026_07_02`

Plan:

1. Reproduce the broken runtime mode where `ops/factory_control.py` is installed
   as `/usr/local/bin/kolibri-factory-control` and cannot import
   `telegram_superfactory`.
2. Repair Factory Control import-path handling for repo, systemd, and
   single-file launcher modes.
3. Add a read-only deploy preflight that checks import path, systemd unit
   contract, and Fabric route surface before live restart.
4. Add focused tests.
5. Push a PR branch only; do not mutate live runtime.

