# Tests

Verification commands run:

```bash
hostname -f || hostname
id -un && uname -a
systemctl show kolibri-factory-control.service -p LoadState -p ActiveState -p SubState -p MainPID -p FragmentPath -p ExecStart -p WorkingDirectory --no-pager
bash /opt/kolibri-ai-platform/scripts/preflight-factory-control-runtime.sh /opt/kolibri-ai-platform
systemctl restart kolibri-factory-control.service
systemctl show kolibri-factory-control.service -p LoadState -p ActiveState -p SubState -p MainPID -p ExecMainStatus --no-pager
base=http://10.99.0.10:9101; for path in /health /v1/health /v1/fabric/health /v1/fabric/routes /v1/fleet/nodes /v1/models; do curl --noproxy '*' -sS -o /tmp/kolibri-route-body -w '%{http_code}' --max-time 4 "$base$path"; done
systemctl show kolibri-telegram-gateway.service -p LoadState -p ActiveState -p SubState -p MainPID -p ExecMainStatus --no-pager
git status --short --branch
```

Observed service state after restart:

```text
MainPID=3588876
ExecStart=/usr/bin/python3 /opt/kolibri-ai-platform/ops/factory_control.py
WorkingDirectory=/opt/kolibri-ai-platform
LoadState=loaded
ActiveState=active
SubState=running
```

Telegram state check:

```text
LoadState=loaded
ActiveState=inactive
SubState=dead
MainPID=0
```

