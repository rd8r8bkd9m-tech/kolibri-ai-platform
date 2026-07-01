# P0 Preserve Dirty Runtime Diffs From main and primary-candidate

## Context

Runtime repos on `main` and `primary-candidate` have dirty changes that may contain hotfixes or drift.

## Scope

- Read-only diff capture.
- Secret redaction.
- Classification as keep/drop/unknown.
- GitHub artifact and issue links.

## Acceptance

- Every dirty file is classified.
- No product code is changed during capture.
- Follow-up PRs are split by subsystem.

## Forbidden

- No git reset/clean.
- No checkout over dirty worktree.
