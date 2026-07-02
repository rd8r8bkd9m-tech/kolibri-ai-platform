# Result

Status: `degraded_not_ready_for_factory_work`

Task id: `P0_AUTOPILOT_EXTRA_32_HOSTVDS_AGENT_10_READINESS_2026_07_02`

Node: `mesh-agent-32`

Agent name: `Владимир - HostVDS Agent 10`

Target node requested: `hostvds-agent-10`

Live Control Plane alias found: `mesh-agent-10`

Readiness summary:

- Remote execution happened on the assigned server-side mesh worker:
  `mesh-agent-32:agent-host-mesh-agent-32`.
- `hostvds-agent-10` is not registered by that exact node id in the current
  `/v1/nodes` snapshot.
- `mesh-agent-10` is registered, fresh, online, not draining, and appears to be
  the live alias for Agent 10.
- `mesh-agent-10` disk: `52327489536` bytes free of `105590231040` bytes total.
- `mesh-agent-10` runner capabilities: `runner:codex`, `runner:mimo`,
  `remote_implementation_runner_ready`, `implementation`,
  `generic_implementation`, `read_only_probe`.
- `mesh-agent-10` Agent Host accepted a direct child probe lease:
  `P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02`.
- Direct child probe completed on `mesh-agent-10`.
- Target-local GitHub auth status: `blocked_gh_missing`; `gh auth status` could
  not run because the `gh` CLI is not installed.
- Target-local runner status: `blocked_runner_missing_or_inactive`; no runner
  systemd unit, runner process, or usual runner install marker was found.
- Target-local disk: `/dev/vda1` ext4, `99G` size, `45G` used, `49G`
  available, `48%`.

Blockers:

- `api_route_endpoint_not_live`: deployed Control Plane returned `404` for
  `/v1/fabric/route` and `/v1/fleet/route`, so API route readiness is degraded
  even though node cards are available through `/v1/nodes`.
- `node_alias_mismatch`: owner-facing requested id is `hostvds-agent-10`, while
  the live runnable node id is `mesh-agent-10`.
- `github_auth_failed`: target-local probe on `mesh-agent-10` reported `gh` is
  not installed, so GitHub auth is not ready for factory work.
- `runner_missing_or_inactive`: target-local probe found no runner service,
  process, or install marker.
- `current_worker_gh_missing`: `gh` is not in `PATH` on `mesh-agent-32`; this is
  not a target-local auth result.

Artifacts:

- `docs/agent/runs/P0_AUTOPILOT_EXTRA_32_HOSTVDS_AGENT_10_READINESS_2026_07_02/PLAN.md`
- `docs/agent/runs/P0_AUTOPILOT_EXTRA_32_HOSTVDS_AGENT_10_READINESS_2026_07_02/ACTIONS.md`
- `docs/agent/runs/P0_AUTOPILOT_EXTRA_32_HOSTVDS_AGENT_10_READINESS_2026_07_02/TESTS.md`
- `docs/agent/runs/P0_AUTOPILOT_EXTRA_32_HOSTVDS_AGENT_10_READINESS_2026_07_02/RESULT.md`
- `docs/agent/runs/P0_AUTOPILOT_EXTRA_32_HOSTVDS_AGENT_10_READINESS_2026_07_02/NEXT.md`
- Child task:
  `P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02`
- Child result reference:
  `/var/lib/kolibri-agent/logical-workers/mesh-agent-10/artifacts/P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02/P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02-attempt-1/result.json`
- Child run docs:
  `docs/agent/runs/P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02/RESULT.md`
  and `docs/agent/runs/P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02/readiness.json`

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_10_FABRIC_ROUTE_AND_GITHUB_AUTH_2026_07_02`

Russian owner-facing summary:

Владислав, проверка выполнена не с Mac, а с серверного worker
`mesh-agent-32`. Узел `hostvds-agent-10` в реестре под таким точным именем не
найден, но живой рабочий alias `mesh-agent-10` онлайн, свежий, с нормальным
диском и заявленными runner-capabilities Codex/MIMO. Главный блокер сейчас не
диск и не lease Agent Host, а деградация API route: production Control Plane
возвращает `404` на route endpoints. Прямая read-only проверка на
`mesh-agent-10` завершилась: GitHub auth не готов, потому что `gh` не
установлен; runner тоже не готов, потому что не найден service/process/install
marker. Следующий шаг - отдельный ремонт Fabric route + GitHub CLI auth +
runner registration.
