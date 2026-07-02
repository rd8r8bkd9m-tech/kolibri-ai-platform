# Safe Remote Agent Launch Plan

Prepared by: `mesh-agent-03`

Task id: `P0_30MIN_MESH_AGENT_03_AGENT_LAUNCH_ACCELERATOR_2026_07_02`

## Launch Rule

Launch remote agents in two phases:

1. Read-only launch wave: classify live state and capacity without mutation.
2. Gated execution waves: run deploy, Telegram, or fanout tasks only after the
   relevant owner/release/canary gate is satisfied.

## First Wave

Task id: `P0_SAFE_REMOTE_AGENT_LAUNCH_WAVE_01_2026_07_02`

Capability: `read_only_probe`

Preferred nodes:

- `primary-candidate`
- `home`
- `mesh-agent-01`
- `mesh-agent-02`
- `mesh-agent-03`

Avoid by default:

- `main`, until runner auth is repaired or a fallback runner is explicitly
  chosen.
- `qjns`, until GitHub credential and MIMO provider blockers are cleared.
- `uiap`, for heavy implementation, until light RAG/knowledge workload limits
  are reconfirmed.

## Required Probe Fields

- Node identity, hostname, clock, uptime, OS, CPU, memory, disk.
- Agent Host service/process state and advertised capabilities.
- Control Plane heartbeat freshness and lease reachability.
- Current checked-out repo path, branch, and commit.
- Factory Control listener, `/health`, `/v1/health`, `/v1/fabric/health`,
  `/v1/fabric/routes`, `/v1/fleet/nodes`, and `/v1/models` status.
- Telegram receiver ownership classification without Bot API mutation.
- Python and Node dependency readiness for focused tests.
- GitHub CLI/API/tooling availability without printing credentials.
- MIMO/Codex/API runner readiness as a classification only; no prompt or secret
  dumps.
- Capacity estimate for safe logical-agent scheduling.
- Required follow-up tasks, each with a separate gate and idempotency key.

## Escalation Gates

| Gate | Required evidence | Allowed next action |
| --- | --- | --- |
| Runtime import-path release | PR/release gate result plus focused tests | Single-node Factory Control canary |
| Factory Control canary | Active service and required `/v1` routes return HTTP 200 | Broader runtime deploy task |
| Telegram receiver safety | Single owner proven, no webhook/poller conflict, owner approval recorded | No-mutation diagnostic or approved controlled start |
| Runner auth/tooling | Node-specific GitHub/MIMO/Codex classifications are green | Direct runner canary |
| Artifact contract | Exact `PLAN/ACTIONS/TESTS/RESULT/NEXT` produced | Mark task complete or dispatch gated follow-up |

## Stop Conditions

- Any task requests `git_push`, `write_worktree`, or `full_autonomy` while also
  declaring read-only/no-push semantics.
- Any command would print secrets, environment dumps, tokens, cookies, or
  credential material.
- Any Telegram action could create a second receiver or mutate Bot API state
  without explicit owner approval.
- Any deploy would replace a live Factory Control entrypoint before the import
  path gate and rollback plan are verified.
- Any verifier path is missing exact canonical artifacts.
