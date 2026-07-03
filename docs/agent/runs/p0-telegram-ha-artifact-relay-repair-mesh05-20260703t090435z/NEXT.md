# Next

1. Deploy with `TELEGRAM_HA_REDIS_URL` set from the existing secret environment, without printing it.
2. Set stable `TELEGRAM_GATEWAY_ID` values for primary and standby instances.
3. Verify Redis keys:
   - `kolibri:telegram:ha:polling_lease`
   - `kolibri:telegram:ha:offset`
   - `kolibri:telegram:ha:notification_spool`
4. Kill or stop the active receiver in a controlled window and confirm standby acquires the lease, keeps the offset monotonic, and drains pending notifications.
5. Keep file-state replication only as fallback if Redis coordination is unavailable.
