# Tests

## Commands Run

```bash
ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o PreferredAuthentications=publickey -o ConnectTimeout=8 -o ConnectionAttempts=1 -o StrictHostKeyChecking=accept-new hostvds-agent-03 'bash -s'
```

Result: failed before remote shell execution with `Connection timed out`.

```bash
python3 ops/kolibri-dispatch nodes
```

Result: passed; Factory Control returned node registry and summary.

```bash
python3 ops/kolibri-dispatch doctor
```

Result: partial pass; repository, control plane, git/python3/ssh/scp checks passed; GitHub CLI check failed because `gh` is not installed on the execution node.

```bash
python3 ops/kolibri-dispatch --control-url http://10.99.0.10:9101 fabric-route mesh-agent-03 --required-capability generic_implementation
python3 ops/kolibri-dispatch --control-url http://10.99.0.10:9101 fabric-route agent-03 --required-capability generic_implementation
python3 ops/kolibri-dispatch --control-url http://10.99.0.10:9101 fabric-route hostvds-agent-03 --required-capability generic_implementation
```

Result:

- `mesh-agent-03`: route `ok`.
- `agent-03`: route `ok` despite stale node card.
- `hostvds-agent-03`: HTTP 503 `target_node_unavailable`.

```bash
for url in http://10.99.0.2:9101 http://10.99.0.10:9101 http://127.0.0.1:9101; do
  for path in /health /v1/health /v1/nodes /v1/fabric/routes /v1/superfactory/status; do
    curl -sS --connect-timeout 2 --max-time 4 -o /dev/null -w '%{http_code}' "$url$path"
  done
done
```

Result:

- `10.99.0.10:9101`: `/health`, `/v1/health`, `/v1/nodes`, `/v1/fabric/routes` passed; `/v1/superfactory/status` returned auth-gated `401`.
- `10.99.0.2:9101`: `/health`, `/v1/health` passed; `/v1/fabric/routes` and `/v1/superfactory/status` returned `404`; `/v1/nodes` timed out in the bounded curl probe.
- `127.0.0.1:9101`: no local listener from this worker context.

```bash
df -hP / /var /var/lib /tmp
systemctl is-active kolibri-agent-host.service
systemctl show kolibri-agent-host.service -p ActiveState -p SubState -p FragmentPath --value
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
```

Result: assigned worker disk and runner service are healthy; branch is `agent/P0_AUTOPILOT_EXTRA_25_HOSTVDS_AGENT_03_READINESS_2026_07_02/generic`, HEAD is `f7ac32c70406432a52752ca45d87e35d9f1facd3`.
