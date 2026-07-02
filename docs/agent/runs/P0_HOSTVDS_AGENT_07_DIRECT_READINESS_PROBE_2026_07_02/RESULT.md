# Result

Status: `readiness_probe_completed_with_blockers`

Node:
- host: `kolibri`
- expected node / agent: `hostvds-agent-07 / mesh-agent-07`
- execution path: `/var/lib/kolibri-agent/logical-workers/mesh-agent-07/worktrees/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02-attempt-1/repo`
- OS user observed by read-only probe: `root`

Task / runner availability:
- current task: `P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02`
- role slot: `autonomous_engineer`
- local Codex runner binary: `present`
- Python runtime: `present`
- curl: `present`
- `kolibri-agent-host.service`: `active`, `enabled`
- `kolibri-factory-control.service`: `active`, `enabled`
- dispatcher queue docs do not list this exact task id, so central task-card visibility for this probe is `not_observed_from_repo_docs`.

Disk:
- filesystem: `/dev/vda1`
- mount: `/`
- total: `99G`
- used: `45G`
- available: `49G`
- use: `48%`

Git / GitHub:
- branch: `agent/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/generic`
- head: `f7ac32c`
- working tree before artifact write: clean
- GitHub CLI: `missing`
- GitHub auth classification: `missing`
- raw auth and credential helper output: not invoked and not recorded

API / Control Plane reachability:
- local listen state includes `10.99.0.10:9101`.
- `http://10.99.0.10:9101/health`: HTTP `200`
- `http://10.99.0.10:9101/v1/health`: HTTP `200`
- `http://10.99.0.10:9101/v1/fabric/health`: HTTP `200`
- `http://10.99.0.10:9101/v1/fabric/routes`: HTTP `200`
- `http://10.99.0.10:9101/v1/fleet/nodes`: HTTP `200`
- `http://10.99.0.10:9101/v1/models`: HTTP `200`
- repo runtime preflight: `factory_control_runtime_preflight=ok`

Blockers:
- GitHub auth is not usable from this node because `gh` is missing; classify as `missing`.
- `127.0.0.1:9101` is not the reachable local Control Plane address; consumers must use the bound local mesh address `10.99.0.10:9101` or fix local aliasing.
- This probe did not observe a central Control Plane task-card entry for the exact task id in `docs/agent/dispatcher/QUEUE.md`.

Artifacts:
- `docs/agent/runs/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/PLAN.md`
- `docs/agent/runs/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/ACTIONS.md`
- `docs/agent/runs/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/TESTS.md`
- `docs/agent/runs/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/RESULT.md`
- `docs/agent/runs/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/NEXT.md`
- `docs/agent/runs/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/SUMMARY_RU.md`

