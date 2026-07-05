# Actions

Actions completed:

1. Submitted
   `P0_DEPLOY_FACTORY_CONTROL_AND_TELEGRAM_GATEWAY_CANARY_REPAIR_2026_07_02`
   with `ops/kolibri-dispatch submit --file`.
2. Control Plane leased the task to `primary-candidate:agent-host-primary`.
3. The remote agent detected that the deployed `/usr/local/bin/kolibri-factory-control`
   was stale versus `origin/main`.
4. The remote agent backed up the old runtime entrypoint to:
   `/var/backups/kolibri-runtime/20260701T2130Z/kolibri-factory-control.before`.
5. The remote agent installed `ops/factory_control.py` over
   `/usr/local/bin/kolibri-factory-control` and restarted
   `kolibri-factory-control.service`.
6. The service failed in an auto-restart loop because the runtime entrypoint
   could not import `telegram_superfactory`.
7. The command-node dispatcher performed emergency rollback:
   - saved the failed entrypoint as
     `/var/backups/kolibri-runtime/20260701T2130Z/kolibri-factory-control.failed-import-telegram-superfactory`;
   - restored
     `/var/backups/kolibri-runtime/20260701T2130Z/kolibri-factory-control.before`;
   - restarted `kolibri-factory-control.service`;
   - verified the mesh health endpoint returned HTTP 200.

No product code was edited locally on Mac.

