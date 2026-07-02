# Result

Status: `blocked_precisely_classified`

Node: server-side worker `mesh-agent-27` on host `kolibri`

Target node: `hostvds-agent-05` / `agent-05` / `mesh-agent-05`

Agent name: `agent-host-mesh-agent-05`

Summary:

- Remote/server-side execution happened from the factory worker environment,
  not from a local Mac product-code edit.
- Direct SSH to `hostvds-agent-05` timed out.
- Control Plane is reachable and healthy at `/health` and `/v1/health`.
- `mesh-agent-05` is online/fresh and has enough disk for factory work.
- Canonical `agent-05` is stale, so the node identity surface is inconsistent.
- A pinned read-only Control Plane task for `mesh-agent-05` was accepted but
  stayed `queued` without `lease_owner`; actual execution on `mesh-agent-05`
  was not proven during this probe window.
- Deployed API route readiness is partial: `/v1/tasks/{task_id}` works, but
  expected `/v1/fleet/*` and `/v1/agents/*` aliases return `404`.
- GitHub auth on the target was not verified. In this worker context, `gh` is
  missing, and no secrets or account details were printed.

Blockers:

1. `hostvds-agent-05` SSH path is unreachable from this worker.
2. `mesh-agent-05` advertises readiness but did not lease the pinned probe.
3. Deployed Control Plane route surface is stale or incomplete for Fabric
   aliases.
4. GitHub CLI/auth readiness is not proven on the target worker.
5. Canonical `agent-05` and mesh `mesh-agent-05` identity cards disagree.

Artifacts:

- `docs/agent/runs/2026-07-02-p0-hostvds-agent-05-readiness/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-05-readiness/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-05-readiness/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-05-readiness/READINESS_MATRIX.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-05-readiness/REMOTE_RESULT.json`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-05-readiness/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-hostvds-agent-05-readiness/NEXT.md`

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_05_LEASE_API_GITHUB_AUTH_2026_07_02`

Russian owner-facing summary:

Владислав, проверка выполнена с серверного worker, не с локального Mac.
`mesh-agent-05` виден в Control Plane как онлайн, с нормальным диском и
заявленными runner-возможностями, но фактическая готовность к работе не
доказана: прямой SSH до `hostvds-agent-05` не проходит, закрепленная read-only
задача для `mesh-agent-05` осталась в очереди без lease, а часть Fabric API
маршрутов на развернутом Control Plane возвращает `404`. Следующий точный шаг:
починить lease/API/GitHub-auth контур для agent-05 и повторить короткий
read-only probe до результата `completed`.

