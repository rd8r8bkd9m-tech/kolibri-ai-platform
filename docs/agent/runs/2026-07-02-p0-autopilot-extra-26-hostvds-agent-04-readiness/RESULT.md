# Result

Status: `completed_with_blockers`

Node:
- Assigned host: `hostvds-agent-04`
- Executed worker: `mesh-agent-04`
- Agent Host: `agent-host-mesh-agent-04`
- Hostname: `kolibri`
- Mesh source node: `agent-04`

Remote execution:
- Completed through Control Plane on `mesh-agent-04`.
- Exact remote task: `P0_AUTOPILOT_EXTRA_26_HOSTVDS_AGENT_04_READINESS_2026_07_02_REMOTE_PROBE`
- Result reference: `/var/lib/kolibri-agent/logical-workers/mesh-agent-04/artifacts/P0_AUTOPILOT_EXTRA_26_HOSTVDS_AGENT_04_READINESS_2026_07_02_REMOTE_PROBE/P0_AUTOPILOT_EXTRA_26_HOSTVDS_AGENT_04_READINESS_2026_07_02_REMOTE_PROBE-attempt-1/result.json`

Readiness:
- Factory work: ready for bounded Control Plane tasks.
- Disk: ready, about 52.3 GB free.
- CPU/RAM: ready for ordinary tasks, not unbounded fanout.
- Runners: `runner:codex` and `runner:mimo` are advertised.
- API route: Control Plane route through `10.99.0.10:9101` is usable for node status and task leasing.

Blockers:
- `ssh_port22_timeout`: direct SSH to `hostvds-agent-04` timed out.
- `github_auth_unverified_on_mesh_agent_04`: safe read-only probe does not expose GitHub auth, and direct SSH was unavailable for a bounded `gh auth status` check.
- `stale_agent_04_metadata_card`: stale `agent-04` card remains; scheduler must use fresh `mesh-agent-04`.
- `transient_control_route_timeout`: one direct `10.99.0.2` node snapshot timed out; `10.99.0.10` route worked.

Artifacts:
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-26-hostvds-agent-04-readiness/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-26-hostvds-agent-04-readiness/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-26-hostvds-agent-04-readiness/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-26-hostvds-agent-04-readiness/READINESS_MATRIX.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-26-hostvds-agent-04-readiness/NEXT.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-26-hostvds-agent-04-readiness/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-26-hostvds-agent-04-readiness/REMOTE_RESULT.json`

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_04_GITHUB_AUTH_AND_SSH_ROUTE_2026_07_02`

Owner-facing summary in Russian:

`hostvds-agent-04` живой как фабричный worker через карточку `mesh-agent-04`: удаленная задача реально выполнилась на `agent-host-mesh-agent-04`, диск и ресурсы достаточные, Codex/MIMO runners заявлены. Для обычных задач его можно использовать через Control Plane. Блокеры: прямой SSH на `31.59.41.146:22` не отвечает, GitHub auth на самом узле пока не подтвержден безопасной проверкой, а старая карточка `agent-04` протухла. Следующая точная задача - безопасно проверить GitHub auth и починить или формально заменить SSH-маршрут.

