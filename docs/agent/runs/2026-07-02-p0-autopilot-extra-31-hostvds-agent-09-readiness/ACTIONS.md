# Actions

Read-only checks performed:

- Confirmed execution context with `hostname`, `uname`, `whoami`, `git rev-parse --show-toplevel`, `git rev-parse --abbrev-ref HEAD`, and `git rev-parse HEAD`.
- Checked disk and inode capacity with `df -h` and `df -i`.
- Checked GitHub CLI availability and auth status with `command -v gh` and `gh auth status`; `gh` is missing, so no token-bearing output was produced.
- Checked local Factory services with `systemctl status kolibri-agent-host.service kolibri-factory-control.service kolibri-mesh-control-bridge.service`.
- Probed Fabric API routes on `10.99.0.10:9101`:
  - `/health`
  - `/v1/health`
  - `/v1/fabric/health`
  - `/v1/fleet/nodes`
  - `/v1/fleet/route?target_node=hostvds-agent-09`
  - `/v1/fleet/route?target_node=hostvds-agent-09&required_capability=generic_implementation`
  - `/v1/fleet/route?target_node=hostvds-agent-09&required_capability=read_only_probe`
  - `/v1/models`
- Queried fleet node cards and found `agent-09` and `mesh-agent-09`, but no canonical `hostvds-agent-09` node id.
- Attempted read-only SSH diagnostic fallback to `hostvds-agent-09` with batch-mode public-key auth only; connection timed out.
- Ran `python3 ops/kolibri-dispatch doctor` and recorded redacted status.

Safety:

- No secrets, environment variables, credentials, or raw auth files were printed.
- No services were restarted.
- No repository history was rewritten.
- No product code was modified.
