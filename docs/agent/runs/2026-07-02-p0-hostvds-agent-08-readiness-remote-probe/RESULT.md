# Result

Status: `degraded`

Node: `mesh-agent-08 / hostvds-agent-08`

Agent name: `Дмитрий - HostVDS Agent 08 Readiness Engineer`

Remote execution:

- Control Plane child task:
  `P0_AUTOPILOT_EXTRA_30_HOSTVDS_AGENT_08_READINESS_REMOTE_PROBE_2026_07_02`
- Lease owner:
  `mesh-agent-08:agent-host-mesh-agent-08`
- Remote artifact:
  `/var/lib/kolibri-agent/logical-workers/mesh-agent-08/artifacts/P0_AUTOPILOT_EXTRA_30_HOSTVDS_AGENT_08_READINESS_REMOTE_PROBE_2026_07_02/P0_AUTOPILOT_EXTRA_30_HOSTVDS_AGENT_08_READINESS_REMOTE_PROBE_2026_07_02-attempt-1/result.json`

Readiness:

- Ready for local Codex artifact work.
- Not ready for full factory work through the expected local Control Plane/Fabric route.
- Disk is healthy: `/dev/vda1` at 48% used, about 49G available.
- Codex is available and auth is classified as configured/provider reachable.
- MIMO binary is available, but auth was not probed to avoid secret/account disclosure.
- GitHub CLI is missing, so `gh auth status` could not run.

Blockers:

- `control_plane_route_unreachable`: `127.0.0.1:9101` refused expected health/Fabric routes while `kolibri-factory-control` reported active.
- `github_cli_missing`: `gh` is not installed, blocking GitHub auth/status and PR workflows.
- `agent_host_service_inactive`: current Codex runner worked, but persistent Agent Host service is inactive.
- `mimo_auth_not_safely_classified`: binary exists, but auth needs a safe non-secret probe.

Artifacts:

- `docs/agent/runs/2026-07-02-p0-hostvds-agent-08-readiness-remote-probe/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-08-readiness-remote-probe/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-08-readiness-remote-probe/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-08-readiness-remote-probe/READINESS_MATRIX.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-08-readiness-remote-probe/REMOTE_RESULT.json`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-08-readiness-remote-probe/NEXT.md`

Russian owner summary:

Проверка выполнена на назначенном рабочем дереве `mesh-agent-08 / hostvds-agent-08`. Диск в норме: занято 48%, свободно около 49G. Codex установлен и авторизация настроена, но ожидаемый локальный маршрут Control Plane/Fabric API на `127.0.0.1:9101` недоступен, хотя systemd-сервис `kolibri-factory-control` показывает `active`. GitHub CLI `gh` отсутствует, поэтому `gh auth status` выполнить нельзя. Agent Host service сейчас `inactive`. Узел пригоден для локальной работы Codex и записи артефактов, но не готов как полноценный factory runner через Control Plane до ремонта маршрута API, `gh` CLI и Agent Host.

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_08_CONTROL_PLANE_ROUTE_AND_GH_CLI_READINESS_2026_07_02`

