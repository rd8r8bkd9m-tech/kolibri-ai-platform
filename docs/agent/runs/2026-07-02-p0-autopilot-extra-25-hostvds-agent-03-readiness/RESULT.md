# Result

Status: `partially_ready_with_route_blockers`

Node: `mesh-agent-25` on server host `kolibri`

Agent: `Алексей - HostVDS Agent 03 Readiness Steward`

Target: `hostvds-agent-03` / `agent-03` / `mesh-agent-03`

## Finding

`hostvds-agent-03` is not ready under its literal host alias because direct SSH timed out and the Fabric route API returns `target_node_unavailable` for `hostvds-agent-03`.

The usable factory target is the mesh shadow `mesh-agent-03`: it is online, fresh, non-draining, idle, has disk headroom, and advertises `generic_implementation`, `read_only_probe`, `runner:codex`, and `runner:mimo`.

The canonical `agent-03` registry entry is stale from `2026-06-30T11:56:41.761600+00:00`, so dispatchers should prefer `mesh-agent-03` until the alias/heartbeat split is repaired.

## Blockers

- `ssh_bootstrap_unreachable`: SSH to `hostvds-agent-03` timed out before remote shell start.
- `canonical_agent_03_stale`: canonical node card is stale and has no hostname/disk/runner detail.
- `literal_hostvds_alias_unregistered`: Fabric route for literal `hostvds-agent-03` returns HTTP 503 `target_node_unavailable`.
- `control_plane_route_drift`: `10.99.0.2:9101` lacks Fabric routes that are present on `10.99.0.10:9101`.
- `github_cli_missing_on_mesh_agent_25`: GitHub CLI is absent on the execution worker, so GitHub auth status cannot be proven from this node.

## Artifacts

- `docs/agent/runs/2026-07-02-p0-autopilot-extra-25-hostvds-agent-03-readiness/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-25-hostvds-agent-03-readiness/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-25-hostvds-agent-03-readiness/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-25-hostvds-agent-03-readiness/READINESS_MATRIX.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-25-hostvds-agent-03-readiness/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-25-hostvds-agent-03-readiness/NEXT.md`
- `docs/agent/runs/2026-07-02-p0-autopilot-extra-25-hostvds-agent-03-readiness/REMOTE_RESULT.json`

## Owner Summary

Проверка выполнена с серверного mesh-воркера `mesh-agent-25`, не с Mac. `hostvds-agent-03` напрямую по SSH недоступен, а буквальный маршрут `hostvds-agent-03` в Fabric API не зарегистрирован. Рабочий путь сейчас есть через `mesh-agent-03`: он онлайн, свободен, с нормальным диском и runner-capabilities `codex`/`mimo`. Для надежной работы нужно починить alias/heartbeat/SSH и отдельно проверить GitHub auth на узле с установленным `gh`.

Next exact task: `P0_REPAIR_HOSTVDS_AGENT_03_ALIAS_AND_SSH_READINESS_2026_07_02`
