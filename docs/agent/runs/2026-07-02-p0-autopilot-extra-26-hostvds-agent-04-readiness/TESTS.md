# Verification

Commands run:

```text
git status --short --branch
rg --files -g '!*node_modules*' -g '!*.png' -g '!*.jpg' -g '!*.jpeg' -g '!*.gif'
ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o PreferredAuthentications=publickey -o ConnectTimeout=8 -o ConnectionAttempts=1 -o StrictHostKeyChecking=accept-new hostvds-agent-04 '<sanitized status probe>'
python3 ops/kolibri-dispatch nodes
python3 ops/kolibri-dispatch --control-url http://10.99.0.10:9101 nodes
python3 ops/kolibri-dispatch submit --file /tmp/kolibri-hostvds-agent-04-probe/envelope.json
python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_26_HOSTVDS_AGENT_04_READINESS_2026_07_02_REMOTE_PROBE
```

Results:

- Direct SSH probe: blocked by timeout to `31.59.41.146:22`.
- Control Plane submission: accepted after required task-contract fields were added.
- Remote execution: completed on `mesh-agent-04:agent-host-mesh-agent-04`.
- Result reference:
  `/var/lib/kolibri-agent/logical-workers/mesh-agent-04/artifacts/P0_AUTOPILOT_EXTRA_26_HOSTVDS_AGENT_04_READINESS_2026_07_02_REMOTE_PROBE/P0_AUTOPILOT_EXTRA_26_HOSTVDS_AGENT_04_READINESS_2026_07_02_REMOTE_PROBE-attempt-1/result.json`
- Node snapshot source: `http://10.99.0.10:9101/v1/nodes`.
- Secret scan intent: artifacts contain no token, key, cookie, password, or environment dump.

