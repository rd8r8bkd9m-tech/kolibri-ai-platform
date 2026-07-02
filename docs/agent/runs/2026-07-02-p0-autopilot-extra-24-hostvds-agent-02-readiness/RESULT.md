# RESULT

Status: `blocked_not_ready_for_factory_work`

Node: `hostvds-agent-02` / `agent-02` / `mesh-agent-02`

Agent name: `Дмитрий - HostVDS Agent-02 Readiness Probe`

Owner-facing summary in Russian:

`hostvds-agent-02` виден в Control Plane как свежий `mesh-agent-02`:
ресурсы достаточные для фабричной работы, диск около 52.3 GB свободно, 8 CPU,
runner capabilities включают Codex и MIMO. Но узел пока нельзя считать готовым:
прямая SSH-проверка до `213.232.204.223:22` завершилась timeout, а задача,
жестко направленная на `mesh-agent-02`, была фактически запущена в worktree
`mesh-agent-24`. GitHub auth на самом hostvds-agent-02 не проверен, потому что
безопасный маршрут на хост недоступен. Следующий шаг - чинить targeted lease/API
route/SSH route, затем повторить redacted GitHub auth and clone probe.

Blockers:

- `targeted_lease_mismatch`: Control Plane accepted `allowed_nodes=["mesh-agent-02"]`
  but the task ran under `mesh-agent-24` artifact/worktree paths.
- `ssh_route_timeout`: bounded SSH probe to `hostvds-agent-02`
  (`213.232.204.223:22`) timed out.
- `fabric_route_missing`: `ops/kolibri-dispatch fabric-routes` returned HTTP 404.
- `github_auth_unknown`: auth status on `hostvds-agent-02` could not be checked
  without a working route.

Artifacts:

- `docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02.json`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-24-hostvds-agent-02-readiness/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-24-hostvds-agent-02-readiness/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-24-hostvds-agent-02-readiness/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-24-hostvds-agent-02-readiness/READINESS_MATRIX.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-24-hostvds-agent-02-readiness/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-24-hostvds-agent-02-readiness/NEXT.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-24-hostvds-agent-02-readiness/REMOTE_RESULT.json`

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_02_TARGETED_LEASE_AND_ROUTE_2026_07_02`
