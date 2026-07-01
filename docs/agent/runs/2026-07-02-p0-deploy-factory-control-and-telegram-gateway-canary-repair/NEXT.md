# Next

Next exact task:

`P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_REPAIR_2026_07_02`

Objective:

Create a remote PR that repairs the Factory Control runtime packaging/import
contract before any further live deploy attempt.

The task must:

1. Reproduce why `/usr/local/bin/kolibri-factory-control` cannot import
   `telegram_superfactory` when it is installed from `ops/factory_control.py`.
2. Add a tested packaging/import-path solution in a server PR branch.
3. Add a deploy-preflight test that would have blocked the broken live deploy.
4. Keep live Factory Control on the rollback entrypoint until the PR is merged
   and a deploy canary passes.
5. Preserve Telegram single receiver safety.

