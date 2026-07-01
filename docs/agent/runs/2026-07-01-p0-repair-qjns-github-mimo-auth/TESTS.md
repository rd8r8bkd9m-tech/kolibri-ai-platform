# Tests

Verification commands run:

```bash
uname -a
./ops/kolibri-dispatch nodes
ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o PreferredAuthentications=publickey -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new kolibri-qjns '...bounded identity probe...'
ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o PreferredAuthentications=publickey -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new root@10.99.0.4 '...bounded identity probe...'
./ops/kolibri-dispatch submit --file /tmp/qjns_mimo_probe.json
./ops/kolibri-dispatch submit --file /tmp/qjns_github_probe.json
./ops/kolibri-dispatch status P0_REPAIR_QJNS_MIMO_PROBE_2026_07_01
./ops/kolibri-dispatch status P0_REPAIR_QJNS_GITHUB_CLONE_PROBE_2026_07_01
./ops/kolibri-dispatch nodes
```

Probe results:

- `P0_REPAIR_QJNS_MIMO_PROBE_2026_07_01`: failed on `qjns:agent-host-qjns`.
- MIMO result reference: `/var/lib/kolibri-agent/artifacts/P0_REPAIR_QJNS_MIMO_PROBE_2026_07_01/P0_REPAIR_QJNS_MIMO_PROBE_2026_07_01-attempt-1/result.json`
- MIMO failure evidence: `mimo-free bootstrap failed: 403 ... code 403 ... type illegal_access`.

- `P0_REPAIR_QJNS_GITHUB_CLONE_PROBE_2026_07_01`: failed on `qjns:agent-host-qjns`.
- GitHub result reference: `/var/lib/kolibri-agent/artifacts/P0_REPAIR_QJNS_GITHUB_CLONE_PROBE_2026_07_01/P0_REPAIR_QJNS_GITHUB_CLONE_PROBE_2026_07_01-attempt-1/result.json`
- GitHub failure evidence: `fatal: could not read Username for 'https://github.com': terminal prompts disabled`.

Final qjns Control Plane node card excerpt:

```json
{
  "active_task": null,
  "agent_id": "agent-host-qjns",
  "disk": {
    "free": 8261197824,
    "total": 20109631488,
    "used": 10953912320
  },
  "health": "online",
  "hostname": "kolibri-tools-executor",
  "node_id": "qjns"
}
```
