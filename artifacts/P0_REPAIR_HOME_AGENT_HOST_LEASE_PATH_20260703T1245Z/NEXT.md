# NEXT.md — Repair Home Agent Host Lease Path

## Follow-up Tasks

1. **SSH key repair**: SSH to 10.99.0.1/178.207.11.90 rejects current keys. Repair SSH credentials for Home node to enable `deploy_home()` to execute without manual intervention.

2. **Systemd unit for Home agent host**: Create `ops/systemd/kolibri-agent-host-home.service` with environment:
   ```
   KOLIBRI_NODE_ID=home
   KOLIBRI_AGENT_ID=home-agent-host
   KOLIBRI_FACTORY_CONTROL_URL=http://10.99.0.2:9101
   KOLIBRI_AGENT_CAPABILITIES=read_only_probe,runner:mimo,generic_implementation
   ```

3. **End-to-end kiosk deploy task test**: Create a `kiosk_deploy` task via `/v1/agents/tasks` with `target_node=home` and `runner=mimo`, verify it gets leased and executed by the Home agent host.

4. **Monitor lease cycle**: After deploying to Home, monitor `/v1/tasks?state=leased` to verify tasks are being picked up by the Home agent host.
