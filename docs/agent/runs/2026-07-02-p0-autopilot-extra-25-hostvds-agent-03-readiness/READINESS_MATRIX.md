# HostVDS Agent 03 Readiness Matrix

| Surface | Status | Evidence | Blocker | Next action |
| --- | --- | --- | --- | --- |
| Server-side execution | Pass | Active task is running on `mesh-agent-25`, host `kolibri`, not a Mac checkout. | None | Continue artifact-only reporting. |
| Direct SSH to `hostvds-agent-03` | Blocked | SSH to `188.130.206.204:22` timed out before remote shell start. | `ssh_bootstrap_unreachable` | Repair SSH reachability or route through Fabric/mesh worker alias. |
| Canonical `agent-03` node card | Blocked/stale | Heartbeat at `2026-06-30T11:56:41.761600+00:00`, health `stale`, hostname missing. | `canonical_agent_03_stale` | Re-register canonical node heartbeat or retire alias in favor of mesh shadow. |
| Mesh shadow `mesh-agent-03` | Pass | Health `online`, fresh heartbeat, active task `null`, capabilities include `generic_implementation`, `read_only_probe`, `runner:codex`, `runner:mimo`; mesh IP `188.130.206.204`. | None for mesh route | Prefer `mesh-agent-03` for factory routing until canonical alias is repaired. |
| Fabric route API | Partial | `mesh-agent-03` route `ok`; `agent-03` route `ok`; literal `hostvds-agent-03` route HTTP 503 `target_node_unavailable`. | `literal_hostvds_alias_unregistered` | Register alias or update dispatcher to target `mesh-agent-03`/`agent-03`. |
| API route | Partial | `10.99.0.10:9101` exposes `/v1/fabric/routes`; `10.99.0.2:9101` still returns `404` for that route. | `control_plane_route_drift` | Use `10.99.0.10:9101` for Fabric routing and repair/retire stale listener on `10.99.0.2`. |
| Disk | Pass | `mesh-agent-03` card reports about 52.29 GB free of 105.59 GB total. Assigned worker `/` is 48% used. | None | No disk repair needed for this readiness decision. |
| Runner status | Pass via node card | `mesh-agent-03` capabilities include `runner:codex`, `runner:mimo`, `remote_implementation_runner_ready`; active task is `null`. | None | Dispatch bounded factory work to `mesh-agent-03` after alias decision. |
| GitHub auth/tooling | Blocked on execution node | `ops/kolibri-dispatch doctor` reports `gh` missing. No token was printed. | `github_cli_missing_on_mesh_agent_25` | Run GitHub auth metadata checks from an authenticated node or install approved `gh` tooling through a separate repair task. |
| Repair task | Required | SSH and literal alias blockers remain; mesh shadow is usable. | See blockers above | `P0_REPAIR_HOSTVDS_AGENT_03_ALIAS_AND_SSH_READINESS_2026_07_02`. |
