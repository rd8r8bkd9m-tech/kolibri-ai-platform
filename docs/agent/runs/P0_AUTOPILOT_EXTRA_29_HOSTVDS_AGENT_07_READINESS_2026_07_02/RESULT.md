# RESULT

Status: `completed_degraded_ready_for_light_factory_work`.

Node:

- Target owner name: `hostvds-agent-07`.
- Current Control Plane node: `mesh-agent-07`.
- Agent host: `agent-host-mesh-agent-07`.
- Hostname from node card: `kolibri`.
- Mesh source node: `agent-07`.
- Mesh IP: `46.8.225.34`.
- Health: `online`.
- Fresh: `true`.
- Active task before child dispatch: `null`.

Resource readiness from Control Plane:

- CPU: `8`.
- Disk from Control Plane: `52326174720` bytes free of `105590231040` bytes total, about 49.6 GiB free.
- Disk from target child probe: `/` is `99G` total, `49G` free, `48%` used.
- RAM: `7799496 kB` available of `12247028 kB` total, about 7.4 GiB available.

Runner readiness from Control Plane:

- Capabilities include `runner:codex`, `runner:mimo`, `generic_implementation`, `read_only_probe`, and `remote_implementation_runner_ready`.
- A direct Codex child probe was accepted, leased to `mesh-agent-07:agent-host-mesh-agent-07`, and completed.
- Child probe reports `codex` present.
- Child probe reports `kolibri-agent-host.service` active/enabled and `kolibri-factory-control.service` active/enabled.

API route:

- `/v1/nodes` works and shows a fresh `mesh-agent-07` card.
- `/v1/tasks` works and leased the direct child probe to `mesh-agent-07`.
- Child probe reports local API reachable on `10.99.0.10:9101`; sampled health/fabric/fleet/model routes returned HTTP `200`.
- Child probe reports `127.0.0.1:9101` does not answer; the working local route is the mesh/control address.
- `/v1/fabric/route` returned HTTP 404 for `mesh-agent-07`; this API route endpoint is not deployed or not exposed on the live Control Plane.

GitHub auth:

- Child probe classified GitHub auth as `missing` because `gh` is not installed in the target environment.
- No credential helpers or raw auth output were invoked.

Blockers:

1. `fabric_route_endpoint_missing`: Control Plane returned HTTP 404 on `/v1/fabric/route`.
2. `direct_ssh_timeout`: documented SSH alias `hostvds-agent-07` timed out on port 22.
3. `github_auth_missing`: `gh` is not installed on `mesh-agent-07`, so non-interactive GitHub auth is unavailable.
4. `stale_alias_card`: old `agent-07` card is stale; current usable identity is `mesh-agent-07`.
5. `localhost_control_alias_missing`: target probe reports `127.0.0.1:9101` does not answer while `10.99.0.10:9101` works.
6. `runner_permission_mismatch`: child envelope requested `no_git_push`, but the child result reports `pushed: true` for its generated docs branch. This was not a push to main and did not modify product code, but the runner contract should be tightened for no-push diagnostic tasks.

Artifacts:

- Parent run docs: `docs/agent/runs/P0_AUTOPILOT_EXTRA_29_HOSTVDS_AGENT_07_READINESS_2026_07_02/`.
- Child envelope: `docs/agent/dispatcher/envelopes/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02.json`.
- Child task id: `P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02`.
- Child lease owner: `mesh-agent-07:agent-host-mesh-agent-07`.
- Child result: `/var/lib/kolibri-agent/logical-workers/mesh-agent-07/artifacts/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02-attempt-1/result.json`.
- Child run docs: `/var/lib/kolibri-agent/logical-workers/mesh-agent-07/worktrees/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02-attempt-1/repo/docs/agent/runs/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/`.
- Child worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-07/worktrees/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02-attempt-1/repo`.
- Child branch publication: child result reports `pushed: true` on branch `agent/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/generic`; no push to main was performed.

Owner-facing Russian summary:

Павел на `hostvds-agent-07` виден в актуальной карточке как `mesh-agent-07`: узел свежий, online, с нормальным запасом диска и RAM, и Control Plane успешно выдал ему прямую задачу. Дочерний probe на самом `mesh-agent-07` завершился: `codex` есть, Agent Host и Factory Control активны, API живет на `10.99.0.10:9101`. Узел можно использовать для легких read-only/diagnostic задач через Control Plane. Для PR/implementation задач с GitHub он пока не готов: `gh` отсутствует, прямой SSH не отвечает, `/v1/fabric/route` на текущем Control Plane возвращает 404, а localhost alias `127.0.0.1:9101` не работает. Отдельный риск: дочерний runner опубликовал docs branch, хотя задача была no-push; это не main и не product code, но контракт no-push нужно усилить. Следующий точный repair: `P0_REPAIR_HOSTVDS_AGENT_07_GITHUB_CLI_AND_LOCAL_CONTROL_ALIAS_2026_07_02`.

No product code was modified. No secrets were printed. No destructive git commands, force push, or push to main were used.
