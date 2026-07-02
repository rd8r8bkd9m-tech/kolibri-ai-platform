# RUNTIME_DEPLOY_PLAN

Status: blocked_not_executed

Target node:

- primary-candidate only.

Current runtime inspection:

- `kolibri-agent-host.service` is active and runs `/usr/local/bin/kolibri-agent-host`.
- `kolibri-factory-control.service` is active and runs `/usr/bin/python3 /opt/kolibri-ai-platform/ops/factory_control.py`.
- `/opt/kolibri-ai-platform` is not a git checkout.
- `/opt/kolibri-ai-platform/ops/agent_host.py` exists but the primary service uses `/usr/local/bin/kolibri-agent-host`.
- `/opt/kolibri-ai-platform/ops/factory_control.py` exists.
- `/opt/kolibri-ai-platform/ops/kolibri-dispatch` was not present.

Pre-deploy health:

- Control Plane HTTP probes to `http://10.99.0.10:9101/health` and `/v1/nodes` timed out.
- Recent Factory Control logs showed `POST /v1/tasks/lease` 500 responses and BrokenPipe traces.

Files that would be eligible for a future PR119-only validation deploy:

- `/usr/local/bin/kolibri-agent-host` from `ops/agent_host.py`.
- `/opt/kolibri-ai-platform/ops/factory_control.py` from `ops/factory_control.py`.
- Do not copy `ops/kolibri-dispatch` unless a later inspection proves a runtime dependency.

Required backup procedure before any future deploy:

```bash
ts="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="/var/backups/kolibri/pr119-heartbeat-${ts}"
mkdir -p "$backup_dir"
cp -a /usr/local/bin/kolibri-agent-host "$backup_dir/kolibri-agent-host"
cp -a /opt/kolibri-ai-platform/ops/factory_control.py "$backup_dir/factory_control.py"
systemctl status --no-pager kolibri-agent-host.service kolibri-factory-control.service > "$backup_dir/pre-status.txt"
```

Future deploy commands, only after PR gate is not blocked and Control Plane is healthy:

```bash
install -m 0755 ops/agent_host.py /usr/local/bin/kolibri-agent-host
install -m 0644 ops/factory_control.py /opt/kolibri-ai-platform/ops/factory_control.py
python3 -m py_compile /usr/local/bin/kolibri-agent-host /opt/kolibri-ai-platform/ops/factory_control.py
systemctl restart kolibri-factory-control.service
systemctl restart kolibri-agent-host.service
systemctl status --no-pager kolibri-factory-control.service kolibri-agent-host.service
curl --max-time 5 http://10.99.0.10:9101/health
```

No deploy was performed in this run.
