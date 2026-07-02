# ROLLBACK_PLAN

Status: not_needed

No runtime deploy was performed, so no rollback was needed.

Rollback procedure for a future PR119 primary-candidate validation deploy:

```bash
backup_dir="/var/backups/kolibri/pr119-heartbeat-YYYYMMDDTHHMMSSZ"
install -m 0755 "$backup_dir/kolibri-agent-host" /usr/local/bin/kolibri-agent-host
install -m 0644 "$backup_dir/factory_control.py" /opt/kolibri-ai-platform/ops/factory_control.py
python3 -m py_compile /usr/local/bin/kolibri-agent-host /opt/kolibri-ai-platform/ops/factory_control.py
systemctl restart kolibri-factory-control.service
systemctl restart kolibri-agent-host.service
systemctl status --no-pager kolibri-factory-control.service kolibri-agent-host.service
curl --max-time 5 http://10.99.0.10:9101/health
```

Rollback trigger conditions:

- Service fails to restart.
- Control Plane health remains unreachable after restart.
- Lease endpoint continues returning 500s attributable to PR119 files.
- Any canary task reaches `dead_letter` due to `lease_expired`.
- Heartbeat failures are not reported as structured `lease_heartbeat_failed`.
