# PR83 Owner Decision Packet

Updated: 2026-07-02T00:00:00Z

Purpose: preserve the PR #83 release-gate record and current post-merge deploy
gate for Agent Host runner contract hardening.

## Current PR State

- PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/83
- Title: `[p0] Harden Agent Host runner contract`
- State: closed
- Merged: true
- Draft: false
- Base: `main`
- Base SHA at merge record: `c915d9a0531ff72eff8856ac6cf7b91677dce0c7`
- Head branch: `p0/agent-host-runner-contract-hardening-2026-06-30`
- Final head SHA: `1b2d34fb7d0dd1248457578291b23a2da1855b64`
- Merge commit SHA: `3416ed1fefea3b399fee3d6f8de55a0ef0f02475`
- Merged at: `2026-07-01T20:21:36Z`

## Evidence

GitHub:

- PR #83 connector metadata reports merged=true.
- Connector review-thread read returned no unresolved review threads.
- `git merge-base --is-ancestor 3416ed1fefea3b399fee3d6f8de55a0ef0f02475 origin/main`
  returned `0`, proving the merge commit is contained by current `origin/main`.
- GitHub compare from merge commit to `main` reports `ahead_by: 13`,
  `behind_by: 0`; current `main` is a descendant of PR #83.
- Combined commit status API returned no legacy statuses for final head or merge
  commit; prior PR comments and PR body record successful GitHub Actions runs.

Server:

- Current task worktree:
  `/var/lib/kolibri-agent/logical-workers/mesh-agent-12/worktrees/P0_EXEC_AGENT_HOST_CONTRACT_DEPLOY_READY_2026_07_02/P0_EXEC_AGENT_HOST_CONTRACT_DEPLOY_READY_2026_07_02-attempt-1/repo`
- Worktree HEAD: `f7ac32c`
- `python3 -m py_compile ops/agent_host.py tests/test_agent_host_runner_contract.py`: passed
- `python3 -m pytest tests/test_agent_host_runner_contract.py -q`: `31 passed in 32.73s`
- `python3 -m pytest tests/test_agent_host* -q`: `44 passed in 42.96s`

Control Plane:

- This packet was refreshed by
  `P0_EXEC_AGENT_HOST_CONTRACT_DEPLOY_READY_2026_07_02`.

## Scope

Merged PR #83 diff was scoped to Agent Host runner contract hardening:

- `.gitignore`
- `ops/agent_host.py`
- `tests/test_agent_host_runner_contract.py`
- `docs/agent/**` runner contract and run artifacts

No additional merge action is required for PR #83.

## Deploy Gate

Deploy-ready source gate: passed.

Runtime deploy gate: blocked until an operator with service access performs the
scoped Agent Host binary/service refresh on each target node and runs the
post-deploy canary. Do not merge or push to `main`; `main` already contains
PR #83.

Exact repair/deploy command for a target node:

```bash
set -euo pipefail
cd /opt/kolibri-ai-platform
git diff --quiet
git diff --cached --quiet
git fetch origin --prune
git checkout main
git pull --ff-only origin main
python3 -m py_compile ops/agent_host.py tests/test_agent_host_runner_contract.py
python3 -m pytest tests/test_agent_host_runner_contract.py -q
sudo install -m 0755 ops/agent_host.py /usr/local/bin/kolibri-agent-host
sudo install -m 0644 ops/systemd/kolibri-agent-host.service /etc/systemd/system/kolibri-agent-host.service
sudo systemctl daemon-reload
sudo systemctl restart kolibri-agent-host.service
sudo systemctl is-active kolibri-agent-host.service
```

Rollback command:

```bash
set -euo pipefail
sudo cp /var/backups/kolibri-agent-host/kolibri-agent-host.before /usr/local/bin/kolibri-agent-host
sudo cp /var/backups/kolibri-agent-host/kolibri-agent-host.service.before /etc/systemd/system/kolibri-agent-host.service
sudo systemctl daemon-reload
sudo systemctl restart kolibri-agent-host.service
sudo systemctl is-active kolibri-agent-host.service
```

Create the backup directory and `.before` files immediately before deploy on
the target node.

## Next Prepared Task

`P0_AGENT_HOST_POST_MERGE_CONTRACT_DEPLOY_CANARY_2026_07_02`

Submit after Agent Host is restarted from current `main` on at least one target
node. The canary should submit no-push/read-only, missing-artifact, write-scope,
and canonical-run-artifact tasks and prove the result status and push fields are
contract-correct.
