# TESTS

Commands run:

```bash
python3 -m json.tool docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02.json >/dev/null
git diff --check -- docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02.json
python3 ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02.json
python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02
ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o PreferredAuthentications=publickey -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new hostvds-agent-02 'printf "node=%s\n" "$(hostname)"; printf "utc=%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; printf "whoami=%s\n" "$(whoami)"'
python3 ops/kolibri-dispatch cancel P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02 --reason target-node-mismatch-ran-on-mesh-agent-24-not-mesh-agent-02
```

Results:

- JSON validation passed.
- `git diff --check` passed for the envelope.
- Control Plane task was accepted.
- Control Plane task was misrouted to `mesh-agent-24`, then cancelled.
- SSH route to `hostvds-agent-02` timed out; no host command output was produced.
