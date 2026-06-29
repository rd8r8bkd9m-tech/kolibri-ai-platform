# Agent Host runner commit result fix

Date: 2026-06-29

## Problem

Remote task `KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN3-20260629` proved that node
`home` can run the full path:

```text
Control Plane -> lease -> Agent Host -> Git SSH clone -> Codex exec -> checks -> commit -> push
```

But the task result stored by Agent Host lost the evidence:

- `commit`: `null`
- `pushed`: `false`
- `changed_files`: `[]`

The remote branch itself proved the commit:

```text
63953f483f52461832ad803a2341c385ac89f590
refs/heads/agent/KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN3-20260629/runtime-smoke
```

Root cause: `run_generic_implementation` only inspected `git status
--porcelain` after the AI runner finished. If Codex/Mimo committed and pushed
inside the task, the worktree was clean, so Agent Host recorded no commit.

## Fix

`ops/agent_host.py` now records the base commit immediately after checkout.
After runner execution and verification:

1. If there are uncommitted files, Agent Host keeps the existing behavior:
   stage, commit, push, and record commit metadata.
2. If the worktree is clean, Agent Host compares `base_commit..HEAD`.
3. If `HEAD` moved, Agent Host records:
   - `commit`
   - `changed_files`
   - whether `origin/<branch>` already points at that commit
4. If the runner committed but did not push and `push=true`, Agent Host pushes
   the branch itself.

This makes runner-created commits first-class factory results instead of hidden
side effects.

## Verification

Local checks:

```bash
python3 -m py_compile ops/agent_host.py tests/test_factory_runtime_queue_contracts.py
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_runtime_queue_contracts.py tests/test_factory_agent_messages.py
git diff --check
```

Result:

```text
10 passed in 0.75s
```

New test:

```text
test_agent_host_detects_runner_committed_and_pushed_changes
```

The test creates a bare origin, a worktree, a base commit, a runner-created
commit, and a pushed branch. It verifies that Agent Host helper functions recover
the changed path and remote branch match even when `git status --porcelain` is
empty.

## Rollout note

Deploy updated `ops/agent_host.py` to execution nodes after commit:

```bash
install -m 0755 ops/agent_host.py /usr/local/bin/kolibri-agent-host
python3 -m py_compile /usr/local/bin/kolibri-agent-host
systemctl restart kolibri-agent-host.service
```

Then rerun a small `generic_implementation` smoke and verify that Control Plane
result includes `commit`, `pushed`, and `changed_files`.
