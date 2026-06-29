# Home result capture rerun 4 evidence

Date: 2026-06-29T06:41:06Z

## Task facts

- Task id: `KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629`
- Node id: `home`
- Runner: `codex`
- Branch: `agent/KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629/result-capture`
- Artifact: `docs/agent-work/home-result-capture-rerun4-20260629.md`

## Generic implementation proof

This is the fourth home generic runtime smoke rerun for the Agent Host result
capture rollout. The task id includes `HOME-GENERIC-RUNTIME-SMOKE-RERUN4`, and
the lease goal is to prove that a live Agent Host returns runner-created commit
metadata after the `generic_implementation` result capture fix.

The prior rollout note in
`docs/agent-work/agent-host-runner-commit-result-fix-20260629.md` asks for a
small `generic_implementation` smoke after deployment and requires Control Plane
results to include `commit`, `pushed`, and `changed_files`. This artifact is
that constrained smoke evidence for node `home`.

## Remote runner proof

This artifact was created inside the Agent Host per-task worktree:

```text
/var/lib/kolibri-agent/worktrees/KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629/KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629-attempt-1/repo
```

Local branch inspection during the lease returned:

```text
agent/KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629/result-capture
```

The only intended repository change is this evidence file under
`docs/agent-work`, created by the remote `codex` runner during the Control Plane
lease.

## Checks run

- `PYTHONPYCACHEPREFIX=/tmp/kolibri-compileall-rerun4 python3 -m compileall -q ops tests`
  - Result: pass, exit code 0.
  - Bytecode was redirected to `/tmp` so the check did not leave generated
    files in `ops` or `tests`.

## Commit and push expectation

The runner should commit this artifact and push:

```text
agent/KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629/result-capture
```

Expected Control Plane result after Agent Host captures the runner-created
commit:

- `changed_files` includes
  `docs/agent-work/home-result-capture-rerun4-20260629.md`
- `commit` is non-empty
- `pushed` is `true`

## Remaining scaling blockers

- Result capture must be observed across more than the current fresh
  `generic_implementation` capacity before treating every factory runner as
  covered.
- Additional `generic_implementation` nodes need fresh heartbeats, version
  parity with the Agent Host fix, and small read-only or smoke probes before
  they take heavier implementation work.
- Heavy app QA, FormulaLM work, benchmarks, production deploys, queue surgery,
  direct Redis or spool edits, service restarts, and Mac compute remain out of
  scope for this lease.
