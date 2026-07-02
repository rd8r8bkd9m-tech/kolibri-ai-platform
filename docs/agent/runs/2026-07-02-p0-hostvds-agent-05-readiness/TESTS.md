# Tests

Commands run:

```bash
hostname && id -un && date -u +%Y-%m-%dT%H:%M:%SZ && df -hP / .
```

Result: server-side worker host `kolibri`, user `root`, disk `/` about `49G`
available, `48%` used.

```bash
ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no \
  -o PreferredAuthentications=publickey -o ConnectTimeout=8 \
  -o ConnectionAttempts=1 -o StrictHostKeyChecking=accept-new \
  hostvds-agent-05 'bash -s'
```

Result: timeout to `31.56.196.10:22`.

```bash
ssh -J kolibri-main -o BatchMode=yes -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no -o PreferredAuthentications=publickey \
  -o ConnectTimeout=8 -o ConnectionAttempts=1 \
  -o StrictHostKeyChecking=accept-new root@31.56.196.10 'hostname'
```

Result: timeout during banner exchange.

```bash
python3 ops/kolibri-dispatch nodes
```

Result: Control Plane reachable; `mesh-agent-05` is online/fresh; canonical
`agent-05` is stale.

```bash
python3 ops/kolibri-dispatch submit
python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_27_HOSTVDS_AGENT_05_READINESS_2026_07_02_REMOTE_PROBE
```

Result: pinned read-only probe accepted by Control Plane but remained `queued`
without `lease_owner`.

```bash
for path in /health /v1/health /v1/fleet/nodes /v1/fleet/route \
  /v1/agents/status/P0_AUTOPILOT_EXTRA_27_HOSTVDS_AGENT_05_READINESS_2026_07_02_REMOTE_PROBE \
  /v1/agents/artifacts/P0_AUTOPILOT_EXTRA_27_HOSTVDS_AGENT_05_READINESS_2026_07_02_REMOTE_PROBE \
  /v1/tasks/P0_AUTOPILOT_EXTRA_27_HOSTVDS_AGENT_05_READINESS_2026_07_02_REMOTE_PROBE
do
  curl -sS -o /dev/null -w '%{http_code}' "http://10.99.0.2:9101$path"
done
```

Result:

- `/health`: `200`
- `/v1/health`: `200`
- `/v1/fleet/nodes`: `404`
- `/v1/fleet/route`: `404`
- `/v1/agents/status/...`: `404`
- `/v1/agents/artifacts/...`: `404`
- `/v1/tasks/...`: `200`

```bash
gh auth status --hostname github.com >/dev/null 2>&1
command -v gh
```

Result: `gh` missing in this worker context; no token or account details
printed.

