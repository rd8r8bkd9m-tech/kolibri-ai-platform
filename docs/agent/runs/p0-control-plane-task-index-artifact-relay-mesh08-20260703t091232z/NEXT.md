# P0 Control Plane Task Index Artifact Relay Next

## Recommended Next Step

Open or update a pull request from `repair/task-index-artifact-relay-mesh08-20260703` if the artifact relay branch is preferred, or from `repair/task-index-reconcile-mesh06-20260703` if only the code repair branch is needed.

## Deployment Notes

- Deploying the repair updates Control Plane task discovery and `/v1/tasks` responses only.
- After deployment, verify `/v1/tasks` and `/v1/tasks?compact=1&summary=1` against a Redis state where a fresh running task exists as `task:<id>` but is missing from `task_ids`.
- Confirm `active_total` does not count completed, failed, cancelled, dead-letter, or expired leased/running records.

## Residual Risk

The code path depends on Redis `SCAN` being available on the active Control Plane Redis backend. If a future backend replaces Redis or restricts `SCAN`, task discovery should expose a backend-native record iterator instead of relying on key scanning.
