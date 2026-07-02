# Tests

Commands executed:

```bash
hostname; whoami; uname -n; date -u +%Y-%m-%dT%H:%M:%SZ
```

Result: host `kolibri`, user `root`, server-side worker path under
`/var/lib/kolibri-agent/logical-workers/mesh-agent-34`.

```bash
curl -sS --max-time 3 http://10.99.0.10:9101/health
curl -sS --max-time 3 http://10.99.0.10:9101/v1/health
```

Result: both returned HTTP `200`; Redis responded `PONG`.

```bash
curl -sS --max-time 3 \
  'http://10.99.0.10:9101/v1/fleet/route?target_node=server-kfrm&required_capability=read_only_probe'
```

Result: status `completed`, node `server-kfrm`, route
`/v1/fleet/route`, next action `dispatch via /v1/agents/tasks`.

```bash
systemctl is-active \
  kolibri-agent-host@mesh-agent-34.service \
  kolibri-factory-control.service \
  kolibri-mesh-control-bridge.service \
  kolibri-telegram-gateway.service \
  kolibri-factory-cluster-monitor.service \
  kolibri-factory-lease-watchdog.service
```

Result, in order: `active`, `active`, `active`, `active`, `activating`,
`inactive`.

```bash
df -h / /var/lib/kolibri-agent .
```

Result: `/dev/vda1` has `49G` available, `48%` used.

```bash
git ls-remote --exit-code origin HEAD
```

Result: exit code `0`; no credential value printed. `gh auth status` could not
be used because `gh` is not installed.

```bash
git diff --name-only
git status --short
```

Result before artifact creation: no product code changes.
