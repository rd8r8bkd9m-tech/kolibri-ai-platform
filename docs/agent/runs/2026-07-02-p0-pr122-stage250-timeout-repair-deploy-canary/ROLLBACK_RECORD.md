# Rollback Record

Rollback state: armed, not used.

Backup directory:

- `/opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout`

Backed up files:

- `/opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout/factory_control.py.before`
- `/opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout/kolibri-factory-control.service.before`

Rollback command:

```bash
cp -a /opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout/factory_control.py.before /opt/kolibri-ai-platform/ops/factory_control.py
cp -a /opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout/kolibri-factory-control.service.before /etc/systemd/system/kolibri-factory-control.service
systemctl daemon-reload
systemctl restart kolibri-factory-control.service
systemctl is-active kolibri-factory-control.service
```

Rollback trigger criteria:

- `python3 -m py_compile` failed.
- Runtime preflight failed.
- Service restart failed.
- Any required route returned non-200.
- Lease canary showed lease 5xx after repair.
- Canary leased a real queued task.

Rollback decision:

- No rollback performed.
- Final service state was `active`.
- Final 250-request lease canary had zero 5xx, zero non-200 responses, zero timeouts, and zero leased tasks.

