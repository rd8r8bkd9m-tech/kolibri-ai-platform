# Result

Status: `failed_useful_report_wrong_artifact_contract`

The remote review produced useful release-steward evidence, but the Control Plane task state is `failed` because exact required run artifacts were not created and the verifier referenced a non-existent envelope path in the clean server worktree.

Remote report summary:

- Inspected known open/stale PR set: 29 PRs.
- Classified PRs into merge, repair, split, blocked, stale/superseded, and deeper-review groups.
- Explained why `main` became stale: PR #95 merged at `2026-07-01T19:05:12Z`, moving `main` from `6d0317c52a9694448ee2c352dc196ce7a27b9487` to `a0d34d6d97a1a2af90463a1205649a24b4a178d7` after other PRs were prepared against the older base.

Important blocker:

- The server-side tool surface could not enumerate all repository PRs reliably. `gh` was missing, unauthenticated REST returned HTTP 404, and the available connector was recent/user-scoped rather than repository-wide.

No GitHub state was mutated by this task.
