# Readiness Matrix

| Surface | Status | Evidence | Blocker | Next action |
| --- | --- | --- | --- | --- |
| Remote execution | ready | Task `P0_AUTOPILOT_EXTRA_26_HOSTVDS_AGENT_04_READINESS_2026_07_02_REMOTE_PROBE` completed on `mesh-agent-04:agent-host-mesh-agent-04`. | none | Use `mesh-agent-04` through Control Plane, not direct SSH. |
| Node identity | ready | `node_id=mesh-agent-04`, `mesh_source_node_id=agent-04`, `hostname=kolibri`, mesh IP `31.59.41.146`. | stale metadata-only `agent-04` card exists. | Route work to `mesh-agent-04`; do not route to stale `agent-04`. |
| Agent name | ready | `agent_id=agent-host-mesh-agent-04`; owner-facing name used: `Дмитрий - Проверка hostvds-agent-04`. | none | Keep Russian display names in owner reports. |
| Disk | ready | Control Plane reports total `105590231040`, used `47883030528`, free `52323074048` bytes. | none for ordinary factory work. | Keep disk guard active before heavy build/model tasks. |
| RAM/CPU | ready | CPU `8`; MemTotal `12247028 kB`; MemAvailable `7950612 kB`. | none for ordinary factory work. | Avoid unbounded fanout without capacity gate. |
| Runner status | ready | Capabilities include `runner:codex` and `runner:mimo`. | Auth quality not proven by read-only probe. | Run bounded runner auth smoke before GitHub/MIMO mutation work. |
| API route | ready with caveat | Control Plane route `http://10.99.0.10:9101/v1/nodes` returned fresh `mesh-agent-04` card; task was leased and completed via Control Plane. | Later `10.99.0.2` node snapshot timed out once. | Prefer `10.99.0.10:9101` route for this node until route freshness is rechecked. |
| GitHub auth | blocked | Safe read-only probe does not expose `gh auth status` or git remote auth; direct SSH status probe timed out. | `github_auth_unverified_on_mesh_agent_04`. | Dispatch exact bounded auth probe task below; do not assign push/review work yet. |
| Direct SSH | blocked | Non-interactive SSH to `hostvds-agent-04` timed out. | `ssh_port22_timeout`. | Repair SSH route or document Control Plane-only access for this worker. |

