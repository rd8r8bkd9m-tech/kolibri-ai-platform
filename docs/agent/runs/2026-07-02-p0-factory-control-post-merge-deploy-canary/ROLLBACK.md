# Rollback

Rollback state: `not_needed`

Backup path:

`/var/backups/kolibri-runtime/20260701T214949Z-P0_FACTORY_CONTROL_POST_MERGE_DEPLOY_CANARY_2026_07_02`

Rollback plan if needed later:

1. Restore `kolibri-factory-control.service.before` to
   `/etc/systemd/system/kolibri-factory-control.service`.
2. Restore `kolibri-factory-control.before` to
   `/usr/local/bin/kolibri-factory-control`.
3. Restore any `*.before` files under matching relative paths in
   `/opt/kolibri-ai-platform`.
4. Run `systemctl daemon-reload`.
5. Restart only `kolibri-factory-control.service`.
6. Verify `/health` and `/v1/health`.

The canary passed, so rollback was not executed.

