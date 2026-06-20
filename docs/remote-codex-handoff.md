# Remote Codex Handoff

This file is the shared context contract for Codex CLI agents running on remote
servers. Read it before taking any task from the lead Codex chat.

## Operating Model

- The Mac Codex Desktop thread is the lead/reviewer/release coordinator.
- Remote Codex CLI instances are bounded executors. They may inspect, plan,
  implement, and report, but they do not deploy or run broad mutations unless
  the current prompt explicitly allows it.
- MiMo Code workers are lower-level bounded agents launched through
  `scripts/mimo_task_runner.py` and task manifests. Do not invoke MiMo through
  ad hoc shell interpolation.
- Prefer asynchronous work: accept a task, run it in tmux, write a structured
  result, and leave enough logs for the lead agent to review later.

## Current Remote Hosts

The fleet registry is `ops/agents.yml`. It currently contains 19 server keys:

- `home`
- `main`
- `uiap`
- `qjns`
- `9fts`
- `kolibri`
- `reserve242`
- `hostvds-highload`
- `hostvds-agent-01`
- `hostvds-agent-02`
- `hostvds-agent-03`
- `hostvds-agent-04`
- `hostvds-agent-05`
- `hostvds-agent-06`
- `hostvds-agent-07`
- `hostvds-agent-08`
- `hostvds-agent-09`
- `hostvds-agent-10`
- `hostvds-paris-highload`

Use `ops/agents.yml` as the source of truth for roles, aliases, health gates,
allowed paths, and MiMo binary paths. Do not hardcode credentials in prompts,
logs, or artifacts.

## Important Context

- The active orchestration branch is `codex/mimo-orchestration`.
- The US backup Codex host is the main reliable remote Codex CLI fallback.
- Home is intended as a long-lived hub, but it has previously had outbound
  network restrictions to OpenAI/GitHub. Treat Home as useful only after egress
  checks pass.
- Hong Kong is not suitable for Codex model work because OpenAI rejected that
  region during setup. Do not store Codex auth there.
- The first safe MiMo experiment is read-only. Start with one server, review
  logs, then scale only after hardening.
- A first read-only MiMo smoke on `hostvds-highload` completed successfully.
  It produced a degraded readiness review and did not modify the read-only
  snapshot.

## Safety Rules

- Never read, print, copy, or log secrets: `.env`, `.ssh`, `.mimocode`,
  `auth.json`, tokens, passwords, private keys, provider credentials.
- Never use `--dangerously-skip-permissions`.
- Never run broad destructive commands such as `pkill`, `rm -rf` outside a
  task-owned run directory, `git reset --hard`, or service restarts unless the
  prompt explicitly authorizes the exact target.
- Do not mutate source datasets. Create derived artifacts in a run directory.
- Do not claim success without metrics, checks, artifacts, and a reviewable
  structured result.
- If a task requires credentials, production deploy, firewall changes, billing,
  or a wider mutation than the prompt allows, stop and report a blocker.

## Repo Entry Points

- `README.md`: product overview.
- `docs/architecture.md`: architecture overview.
- `docs/backend.md`: backend context.
- `docs/frontend.md`: frontend context.
- `docs/orchestration.md`: existing orchestration guide.
- `ops/agents.yml`: server registry.
- `ops/task_manifest.schema.json`: existing task manifest contract.
- `scripts/mimo_task_runner.py`: safe MiMo/OpenClaw runner.
- `scripts/prepare_mimo_worktrees.py`: creates sanitized remote read-only
  worktree snapshots.
- `ops/tasks/mimo-18-readonly/`: read-only MiMo manifests.

## FormulaLM Protocol Direction

The requested FormulaLM orchestration work is:

- Add root `AGENTS.md` making Codex the master FormulaLM experiment
  orchestrator and MiMo Code workers bounded executors.
- Add worker artifacts under `ops/formulalm/`:
  `worker_prompt.md`, `task_envelope.schema.json`, `status.schema.json`,
  `result.schema.json`.
- Add `ops/experiments/estimate-pilot-001/role_map.json` covering all 19
  servers from `ops/agents.yml`.
- Update `docs/orchestration.md` to distinguish the existing operational guide
  from 19-node FormulaLM experiment mode.
- Preflight comes before training: inventory servers, verify repo/envs, locate
  estimate files, inspect schemas, create SHA-256 dataset manifest, audit
  duplicates/PII/leakage, propose canonical JSON, create grouped
  train/validation/final-test split, and run leakage tests.
- Do not start training or server mutation while only adding repo instructions
  and schemas.

## Result Contract

Every remote task should end with a concise structured result:

```json
{
  "status": "completed | failed | blocked | degraded",
  "summary": "What was done and what it means.",
  "changed_files": [],
  "checks": [],
  "risks": [],
  "artifacts": [],
  "next_action": "The next reviewable step."
}
```

If you run a long task in tmux, write the final result to a log file under
`logs/agent-runs/` or a task-owned run directory and leave the path visible in
the terminal.

## How To Accept Work From Lead Codex

1. Read this file and any task-specific prompt.
2. Run `git status --short --branch` before edits.
3. Ignore unrelated dirty files; do not revert user or other-agent work.
4. Keep changes scoped to the requested task.
5. Run the smallest meaningful checks.
6. Report result with files, checks, risks, artifacts, and next action.
