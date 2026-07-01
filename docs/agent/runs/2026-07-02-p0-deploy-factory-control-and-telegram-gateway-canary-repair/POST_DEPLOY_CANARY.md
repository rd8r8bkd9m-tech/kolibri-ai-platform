# Post Deploy Canary

Status: `failed_rollback_restored_control_plane`

The live deploy attempt did not pass the post-deploy canary.

Canary after rollback:

- `kolibri-factory-control.service`: `active/running`.
- `http://10.99.0.10:9101/health`: HTTP `200`.
- `http://10.99.0.10:9101/v1/health`: HTTP `200`.
- `http://10.99.0.10:9101/v1/fabric/health`: HTTP `404`.
- `http://10.99.0.10:9101/v1/fabric/routes`: HTTP `404`.
- `http://10.99.0.10:9101/v1/fleet/nodes`: HTTP `404`.
- `http://10.99.0.10:9101/v1/models`: HTTP `404`.

Rollback paths:

- Good backup restored from:
  `/var/backups/kolibri-runtime/20260701T2130Z/kolibri-factory-control.before`.
- Failed deployed entrypoint saved to:
  `/var/backups/kolibri-runtime/20260701T2130Z/kolibri-factory-control.failed-import-telegram-superfactory`.

Do not retry live deploy until
`P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_REPAIR_2026_07_02` passes.

