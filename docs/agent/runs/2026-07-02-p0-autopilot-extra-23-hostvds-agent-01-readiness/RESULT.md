# Result

Status: `completed_readiness_snapshot_with_blockers`.

Owner-facing summary in Russian:

Проверка выполнена с серверного worker `mesh-agent-23` по данным Control Plane. `hostvds-agent-01` представлен живой карточкой `mesh-agent-01`: node свежий, online, не drain, без активной задачи, с `runner:codex` и `runner:mimo`, диском около 52.3 GB свободно из 105.6 GB. Control Plane API живой: `/health` и `/v1/health` отвечают `200 ok`, Redis отвечает `PONG`. Полная готовность для factory work пока не доказана, потому что GitHub auth и реальный Codex/MIMO auth на самом `mesh-agent-01` не проверены, а повторный self-submit с тем же task id остался в текущем lease `mesh-agent-23`. Для безопасного допуска нужен отдельный read-only canary с уникальным task id, который будет арендован именно `mesh-agent-01`.

Structured facts:

- Task id: `P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02`
- Probed node: `mesh-agent-01`
- Requested agent name: `Иван — HostVDS Agent Readiness Inspector`
- Requested worker identity: hostvds-agent-01 / `agent-host-mesh-agent-01`
- Assigned Control Plane lease node for this run: `mesh-agent-23`
- Assigned Control Plane lease agent: `agent-host-mesh-agent-23`
- Current task state observed during probe: `running`
- Result reference: `null` at last poll
- Remote execution proof: task heartbeat and active task exist on server-side mesh worker `mesh-agent-23`
- Direct target-node execution proof: not proven; this run is a readiness snapshot from the assigned server-side worker

hostvds-agent-01 readiness snapshot:

- Canonical live card: `mesh-agent-01`
- Metadata alias: `agent-01` is stale
- Health: `online`
- Fresh: `true`
- Draining: `false`
- Active task: `null`
- Hostname: `kolibri`
- Capabilities: `mesh`, `mesh_node`, `implementation`, `generic_implementation`, `read_only_probe`, `remote_implementation_runner_ready`, `runner:codex`, `runner:mimo`
- Disk: 105590231040 bytes total, 47942283264 bytes used, 52263821312 bytes free
- RAM: `MemTotal=12247028 kB`, `MemAvailable=9346500 kB` at sampled node card
- GitHub auth: not verified on `mesh-agent-01` because the full probe did not execute there
- API route/control-plane reachability: `/health` and `/v1/health` returned `200 ok`; Redis queue backend responded `PONG`; `fabric-routes` helper returned HTTP `404`
- Runner status: capabilities advertise `runner:codex` and `runner:mimo`; direct runner auth was not verified on `mesh-agent-01`

Blockers:

- `target_github_auth_unverified`: GitHub auth status on `mesh-agent-01` is not proven.
- `target_runner_auth_unverified`: Codex/MIMO auth on `mesh-agent-01` is not proven beyond advertised capabilities.
- `metadata_alias_stale`: legacy `agent-01` card is stale and should not be used as the readiness source.
- `fabric_routes_helper_unavailable`: `/v1/fabric/routes` returned HTTP `404`; use `/health`, `/v1/health`, `/v1/nodes`, and exact task routes until deployed route support is repaired.

Artifacts:

- Dispatcher envelope: `docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02.json`
- Run docs: `docs/agent/runs/2026-07-02-p0-autopilot-extra-23-hostvds-agent-01-readiness/`
- Control Plane task worktree observed: `/var/lib/kolibri-agent/logical-workers/mesh-agent-23/worktrees/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02-attempt-1/repo`
- Control Plane log paths observed: `/var/lib/kolibri-agent/logical-workers/mesh-agent-23/artifacts/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02-attempt-1/`

Next exact task:

`P0_HOSTVDS_AGENT_01_DIRECT_AUTH_AND_RUNNER_CANARY_2026_07_02`

Objective: submit a unique read-only canary targeted to `mesh-agent-01` only, verify the lease/worktree/log paths are on `mesh-agent-01`, run redacted `gh auth status`, `codex --version`, `mimo --version`, and a non-secret runner/auth smoke if available, then return a Russian owner-facing readiness verdict. Do not modify code, credentials, services, or GitHub state.
