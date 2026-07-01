# Result

Status: `dead_letter_rollback_applied`

Task id: `P0_DEPLOY_FACTORY_CONTROL_AND_TELEGRAM_GATEWAY_CANARY_REPAIR_2026_07_02`

Control Plane status:

- State: `dead_letter`.
- Error type: `lease_expired`.
- Error: `lease expired and retry budget exhausted`.
- Lease owner: `primary-candidate:agent-host-primary`.

Runtime result:

- The remote agent attempted a live Factory Control entrypoint deploy.
- The deployed entrypoint failed with:
  `ModuleNotFoundError: No module named 'telegram_superfactory'`.
- The service entered `activating/auto-restart`.
- Agent Host could not post heartbeat/fail while Factory Control was down:
  `Connection refused`.
- The command-node dispatcher restored the backup entrypoint.
- After rollback, `kolibri-factory-control.service` returned to
  `active/running`.
- After rollback, mesh `/health` returned HTTP `200`.

Remaining blockers:

- Live Factory Control is restored but still stale: PR #85 Fabric routes return
  HTTP `404`.
- Runtime packaging/import path is not ready for deploying
  `ops/factory_control.py` as `/usr/local/bin/kolibri-factory-control`.
- Telegram gateway remains inactive on the probed node; do not start it until
  single receiver ownership is proven.
- Control Plane/Agent Host finalization is fragile when Factory Control goes
  down during a task.

Next exact task:

`P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_REPAIR_2026_07_02`

