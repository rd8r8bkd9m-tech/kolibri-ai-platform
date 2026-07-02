# RESULT

Status: `blocked`

Node and agent:

- Probe execution node: `kolibri`
- Probe execution agent: `mesh-agent-28:agent-host-mesh-agent-28`
- Target node: `hostvds-agent-06`
- Target role alias: `docs-knowledge`

Readiness classification:

- Remote execution path to the assigned worker lease: confirmed on server-side
  worker `mesh-agent-28`.
- Direct target execution on `hostvds-agent-06`: blocked; SSH BatchMode timed
  out on port 22 before any remote command could run.
- API route: blocked; live Control Plane health is available, but Fabric route
  endpoints required for node routing return HTTP 404 and `/v1/nodes` times out.
- GitHub auth on target: unknown; target host was unreachable, so `gh auth
  status` could not execute there.
- Disk on target: unknown; target host was unreachable, so `df -hP /` could not
  execute there.
- Runner status on target: unknown; target host was unreachable and node API
  status was not available.
- Current task runner status: running under
  `mesh-agent-28:agent-host-mesh-agent-28`.

Blockers:

1. `hostvds_agent_06_ssh_timeout`: direct noninteractive SSH to
   `hostvds-agent-06` timed out.
2. `fabric_route_api_not_deployed`: checked-in `ops/factory_control.py`
   contains Fabric route endpoints, but the live Control Plane returns 404 for
   `/v1/fleet/route`, `/v1/fabric/routes`, and `/v1/fabric/health`.
3. `node_status_endpoint_timeout`: `/v1/nodes` did not return within the bounded
   8 second probe window.
4. `target_runtime_unproven`: target disk, GitHub auth, Agent Host service, and
   runner state remain unverified because no command reached the host.

Artifacts:

- `docs/agent/runs/2026-07-02-p0-hostvds-agent-06-readiness/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-06-readiness/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-06-readiness/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-06-readiness/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-06-readiness/NEXT.md`
- `artifacts/P0_AUTOPILOT_EXTRA_28_HOSTVDS_AGENT_06_READINESS_2026_07_02/repair-task.json`

Next exact task: `P0_REPAIR_HOSTVDS_AGENT_06_ROUTE_AUTH_DISK_RUNNER_2026_07_02`

Owner-facing summary in Russian:

`hostvds-agent-06` сейчас не готов к фабричной работе. Задача выполнялась не с
локального Mac, а с серверного агента `mesh-agent-28`. До целевого сервера
команда не дошла: SSH по безопасному неинтерактивному маршруту завершился
таймаутом. Живой Control Plane отвечает на health, но нужные Fabric API маршруты
для выбора/ремонта узла не развернуты или не обслуживаются текущим процессом.
Диск, GitHub-авторизация и Agent Host на `hostvds-agent-06` остаются
неподтвержденными до восстановления маршрута.
