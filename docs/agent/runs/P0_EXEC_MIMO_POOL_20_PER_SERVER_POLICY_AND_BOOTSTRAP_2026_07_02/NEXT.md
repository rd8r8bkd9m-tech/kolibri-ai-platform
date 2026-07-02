# Next

Exact next task:

`P0_DEPLOY_MIMO_POOL_POLICY_CANARY_2026_07_02`

Objective:

Deploy this branch to one non-primary Agent Host node, install `ops/systemd/kolibri-agent-host@.service` and `ops/kolibri-agent-pool`, run `systemctl daemon-reload`, start two canary slots with `ops/kolibri-agent-pool start 2`, verify `/v1/nodes` and `/api/factory/status` show capped `agent_pool` capacity, then stop canary slots or roll forward to 20 only after owner approval.

Exact canary commands after code is present on the target node:

```bash
sudo install -m 0644 ops/systemd/kolibri-agent-host@.service /etc/systemd/system/kolibri-agent-host@.service
sudo install -m 0755 ops/kolibri-agent-pool /opt/kolibri-ai-platform/ops/kolibri-agent-pool
sudo systemctl daemon-reload
sudo /opt/kolibri-ai-platform/ops/kolibri-agent-pool start 2
curl -fsS http://127.0.0.1:9101/v1/nodes
sudo /opt/kolibri-ai-platform/ops/kolibri-agent-pool status 2
```

Rollback:

```bash
sudo /opt/kolibri-ai-platform/ops/kolibri-agent-pool stop 2
sudo rm -f /etc/systemd/system/kolibri-agent-host@.service
sudo systemctl daemon-reload
```
