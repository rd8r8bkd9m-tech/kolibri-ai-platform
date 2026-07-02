# Actions

Live control route discovery:

- `http://127.0.0.1:9101` was not listening from this worker.
- `http://10.99.0.2:9101` and `http://control.kolibri.internal:9101` answered `/health` and `/v1/health`, but returned `404` for the current Fabric routes.
- `http://10.99.0.10:9101` answered `/v1/fabric/health`, `/v1/fleet/nodes`, `/v1/fleet/route`, `/v1/agents/status/...`, and `/v1/agents/tasks`.

Active GoMesh development agent evidence:

- Prior GoMesh supervisor task: `P0_GOMESH_READONLY_ROLLUP_AND_SUBAGENT_CONTROL_2026_07_01`.
- Prior agent display name: `Николай — GoMesh Safety Supervisor`.
- Prior target node: `primary-candidate / Primorye`.
- Prior active worktree from task context: `/opt/kolibri/repo`.
- Prior active branch from task context: `codex/gomesh-docs-rollout-safety`.
- Prior task state: `completed`.
- Prior lease owner: `primary-candidate:agent-host-primary`.
- Prior result artifact: `/var/lib/kolibri-agent/artifacts/P0_GOMESH_READONLY_ROLLUP_AND_SUBAGENT_CONTROL_2026_07_01/P0_GOMESH_READONLY_ROLLUP_AND_SUBAGENT_CONTROL_2026_07_01-attempt-1/result.json`.

Current primary-candidate status:

- `primary-candidate` is online.
- Current agent id: `agent-host-primary`.
- Capabilities include `implementation`, `review`, `generic_implementation`, `generic_review`, `runner:codex`, and `runner:mimo`.
- Current active task: `P0_30MIN_12AGENT_11_ARTIFACT_RELAY_STEWARD_2026_07_02`.

Direct owner-rules handoff:

- Submitted `P0_GOMESH_OWNER_RULES_MONITOR_REVIEW_LOOP_2026_07_02` through `POST /v1/agents/tasks` on `http://10.99.0.10:9101`.
- Target node: `primary-candidate`.
- Runner: `codex`.
- Agent display name: `Николай - GoMesh Owner Rules Monitor`.
- The task includes owner rules forbidding mixed PRs, dirty runtime checkout mutation, destructive git commands, force push, push to `main`, and secret output.
- The task requires remote run artifacts: `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, `NEXT.md`, `MONITORING_LOOP.md`, and `OWNER_RULES.md`.
- The task enables `create_review_on_complete` so a PR URL in the result triggers the existing review-task path.

Immediate handoff status:

- The handoff task was accepted with HTTP `201`.
- Created task state after submission: `queued`.
- Three short polls still showed `queued`, with no lease owner yet.
