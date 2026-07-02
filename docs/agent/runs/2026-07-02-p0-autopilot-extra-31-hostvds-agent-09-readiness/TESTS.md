# Tests

Verification commands run:

```bash
hostname; uname -a; whoami; id -un; git rev-parse --show-toplevel; git rev-parse --abbrev-ref HEAD; git rev-parse HEAD
df -h / /var/lib/kolibri-agent
df -i / /var/lib/kolibri-agent
command -v gh || true
gh auth status
systemctl --no-pager --plain status kolibri-agent-host.service kolibri-factory-control.service kolibri-mesh-control-bridge.service
curl --max-time 5 http://10.99.0.10:9101/health
curl --max-time 5 http://10.99.0.10:9101/v1/health
curl --max-time 5 http://10.99.0.10:9101/v1/fabric/health
curl --max-time 5 http://10.99.0.10:9101/v1/fleet/nodes
curl --max-time 5 'http://10.99.0.10:9101/v1/fleet/route?target_node=hostvds-agent-09'
curl --max-time 5 'http://10.99.0.10:9101/v1/fleet/route?target_node=hostvds-agent-09&required_capability=generic_implementation'
curl --max-time 5 'http://10.99.0.10:9101/v1/fleet/route?target_node=hostvds-agent-09&required_capability=read_only_probe'
curl --max-time 5 http://10.99.0.10:9101/v1/models
ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o PreferredAuthentications=publickey -o ConnectTimeout=8 -o ConnectionAttempts=1 -o StrictHostKeyChecking=accept-new hostvds-agent-09 'bash -s'
python3 ops/kolibri-dispatch doctor
```

Results:

- Server-side execution confirmed on node `kolibri`, worktree `logical-workers/mesh-agent-31/.../repo`.
- Control plane on `10.99.0.10:9101` is reachable and returns success for `/health`, `/v1/health`, `/v1/fabric/health`, `/v1/fleet/nodes`, and `/v1/models`.
- Fabric route to `hostvds-agent-09` returns `503` with `blocked_reason=target_node_unavailable`.
- Fleet registry has `agent-09` and `mesh-agent-09`; it has no canonical `hostvds-agent-09` node card.
- SSH fallback to `hostvds-agent-09` times out on port 22.
- Executing worker disk is healthy: root filesystem `99G` total, `45G` used, `49G` available, `48%` used; inodes `19%` used.
- `kolibri-agent-host.service`, `kolibri-factory-control.service`, and `kolibri-mesh-control-bridge.service` are active on the executing node.
- GitHub auth cannot be verified on this node because `gh` is not installed.
