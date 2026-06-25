# Kolibri Execution Contract Override

This file is the durable execution contract for the Kolibri project. It is
loaded by `AGENTS.md` and must be treated as active instructions by every new
Codex session in this repository.

## Orchestration Authority

- Codex is the single chief orchestrator for Kolibri.
- Do not use built-in Codex subagents to implement tasks.
- A real implementation agent is only a remote server-side process with all of:
  `node_id`, `agent_id`, `task_id`, PID or container ID, worktree, branch,
  heartbeat, log path, and result artifact.
- Chat memory is not the source of truth. Durable state, logs, task envelopes,
  and result artifacts must live in repository or factory files.

## Preauthorized Reversible Actions

Within this repository and the owned server infrastructure, reversible
orchestration actions are preauthorized:

- SSH through configured keys.
- Backup and restore points.
- Git branches, worktrees, commits, staging, PRs, and rollback branches.
- Dependency installation.
- Docker and service orchestration.
- systemd or launchd service starts/stops/restarts where applicable.
- Tests, smoke checks, canaries, staging, rollback, drain, and quarantine.
- Remote worker launch only when it records a real process identity and result.

Do not pause at planning when a reversible execution step is available.

## Credential And Secret Handling

- Never place passwords, private keys, API keys, provider credentials, tokens,
  or VPN credentials in prompts, argv, logs, Git, temporary files, or result
  artifacts.
- Do not read secret-bearing files such as `.env`, `.ssh`, `.mimocode`,
  `auth.json`, private keys, password stores, or provider credential files.
- For password-only SSH, stop at an interactive credential checkpoint, install a
  public key after the credential is provided out-of-band, then continue
  key-only.
- Remote commands must avoid printing environment variables or credential paths.

## Remote Agent Contract

Every remote task must produce a structured execution record containing:

- `node_id`
- `agent_id`
- `task_id`
- PID or container ID
- worktree path
- branch name
- heartbeat location and timestamp
- log path
- result artifact path
- changed files
- checks/tests
- risks
- recommended next action

Workers do not merge, deploy to production, or mutate shared state unless the
task envelope explicitly allows that scope and Codex records the action.

## Git Integration Contract

The project owner is the Product Owner, Vision Owner, and Final Design
Authority. The owner must not be required to manually manage branches,
worktrees, rebases, merge conflicts, or cleanup. Codex must hide Git mechanics
behind task IDs and product-level statuses.

- `main` is always protected and must remain working.
- Direct commits to `main` are forbidden.
- One implementation task maps to one short-lived branch.
- One task has one responsible agent.
- One branch has one local worktree on one node.
- Every change goes through a pull request.
- Every pull request is updated against the latest `main`.
- Merges run through a sequential merge queue.
- After merge, the branch and worktree are cleaned up automatically.
- Production releases are made only from version tags.
- Unfinished features are hidden behind feature flags.
- UI changes require screenshots and visual regression.
- Design system changes require a separate explicit scope.
- Changes with no user-visible effect may be accepted automatically after all
  gates pass.
- Product, UX, calculation, and data changes require an owner decision.

User-facing task reports must show:

- goal
- task ID
- status
- preview
- tests
- risks
- accepted decision
- production result

Do not make the owner choose Git operations. During parallel work, Codex must
detect file overlap, serialize conflicting tasks, run only independent changes
in parallel, and never use a shared writable worktree.

The current approved interface is the design baseline. Any unplanned visual
difference blocks merge.

## Reporting Format

Every orchestration report must use this shape:

```text
STATUS:
CURRENT_PHASE:
DONE:
ACTIVE_REMOTE_TASKS:
NODES:
AGENTS:
EVIDENCE:
COMMITS:
PULL_REQUESTS:
TESTS:
DEPLOYMENTS:
FAILURES:
BLOCKERS:
NEXT_EXECUTING:
```

## Safety Boundary

- Irreversible destructive deletion, external disclosure, paid scaling, and
  credential exposure are not covered by reversible preauthorization.
- If a remote worker asks to access secrets or operate outside its allowed path,
  it must stop and report `blocked`.
- Factory and server reports should summarize conclusions and link artifacts,
  not dump raw logs into user-facing messages.
