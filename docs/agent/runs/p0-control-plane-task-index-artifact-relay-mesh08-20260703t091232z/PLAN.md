# P0 Control Plane Task Index Artifact Relay Plan

Task: `P0_CONTROL_PLANE_TASK_INDEX_ARTIFACT_RELAY_MESH08_20260703T091232Z`

Timestamp: 2026-07-03T09:12:32Z

## Objective

Recover the useful work from `P0_CONTROL_PLANE_TASK_INDEX_RECONCILE_MESH06_20260703T090521Z`, which produced a valid repair branch but failed its wrapper because the exact required run artifacts were missing.

## Plan

1. Locate the prior MESH06 worktree and artifact output.
2. Verify the prior repair was committed and pushed.
3. Clone the pushed repair branch into this MESH08 run worktree.
4. Re-run focused and adjacent tests in the MESH08 worktree.
5. Add the exact required run artifacts under this task run directory.
6. Verify every required artifact with `test -s`.
7. Commit and push a relay branch without pushing to `main`.

## Reused Work

The preserved repair is branch `repair/task-index-reconcile-mesh06-20260703`, commit `4920ec6 Reconcile control plane task indexes`.
