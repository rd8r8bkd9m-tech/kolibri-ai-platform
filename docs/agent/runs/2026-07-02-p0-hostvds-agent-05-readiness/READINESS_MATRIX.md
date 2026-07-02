# Readiness Matrix

| Area | Status | Evidence | Blocker |
| --- | --- | --- | --- |
| Assigned worker execution | `done` | This run executed on server-side host `kolibri`, logical worker `mesh-agent-27`. | None for this worker. |
| Direct hostvds-agent-05 SSH | `blocked` | TCP/SSH to `31.56.196.10:22` timed out; jump through `kolibri-main` also timed out. | SSH path/firewall/banner reachability. |
| Control Plane health | `ready` | `http://10.99.0.2:9101/health` and `/v1/health` returned `200`. | None for health route. |
| API route surface | `partial` | `/v1/tasks/{task_id}` returned `200`; `/v1/fleet/*` and `/v1/agents/*` aliases returned `404` on deployed Control Plane. | Deployed runtime is missing or not exposing expected Fabric aliases. |
| Canonical `agent-05` card | `stale` | Last heartbeat `2026-06-30T11:56:42.103679+00:00`, health `stale`. | Stale canonical node identity. |
| Mesh `agent-05` shadow | `online` | `mesh-agent-05` fresh heartbeat, source `agent-05`, mesh IP `31.56.196.10`. | Shadow is healthy, but pinned task did not lease during probe window. |
| Disk | `ready` | `mesh-agent-05` reports about `52.3 GB` free of `105.6 GB`; current server worker `/` about `49 GB` free. | None observed. |
| Runner status | `partial` | `mesh-agent-05` advertises `runner:codex`, `runner:mimo`, and `remote_implementation_runner_ready`. | Actual pinned read-only task stayed queued, so execution path is not proven. |
| GitHub auth/tooling | `blocked` | Current server worker has no `gh` binary. `mesh-agent-05` advertises `github_review`, but auth was not directly verified. | Install/verify `gh` and GitHub auth on the target worker without printing secrets. |
| Factory work readiness | `blocked_for_agent_05` | Control Plane sees `mesh-agent-05` online, but exact pinned task has no `lease_owner`. | Queue/lease routing or worker polling mismatch for `mesh-agent-05`. |

