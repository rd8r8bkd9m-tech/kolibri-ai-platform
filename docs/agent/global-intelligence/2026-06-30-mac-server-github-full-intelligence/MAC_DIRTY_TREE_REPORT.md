# Mac dirty tree report

## Current status

`git status --short --branch`:

```text
## HEAD (no branch)
?? docs/
```

## Diff classification

- tracked diff: empty.
- staged diff: empty.
- product code modified: no.
- generated docs/artifacts: yes, under `docs/`.

## Risk

Current dirty tree is acceptable for this task because the requested output is documentation under `docs/agent/global-intelligence/...`.

Future branch operations must not happen in this worktree until the docs are either committed/staged intentionally or moved to a safe artifact branch/worktree.

## Server dirty trees

Server runtime dirty states are separate and higher risk:

- `main` server runtime repo has modified `ops/factory_control.py`, `ops/mesh_control_bridge.py`, plus a backup file.
- `primary-candidate` runtime repo has dirty tracked files across backend, infra, ops and tests.
