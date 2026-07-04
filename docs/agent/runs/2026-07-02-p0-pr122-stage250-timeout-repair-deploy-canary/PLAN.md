# Plan

Task: `REBROADCAST_P0_PR122_STAGE250_TIMEOUT_REPAIR_DEPLOY_AND_CANARY_2026_07_02-DELIVERABLE-RETRY`

Goal: run a rollback-protected runtime canary for PR #125 / PR #122 stage-250 lease timeout repair without requeueing a full worker wave.

1. Confirm the rebroadcast lease is running on a healthy node from `allowed_nodes` and do not mutate the original task.
2. Fetch PR #125 head and merge refs for source-of-truth commit evidence.
3. Verify rollback materials exist for the live Factory Control runtime before relying on the deployed repair.
4. Confirm the live Control Plane exposes the PR #125 lease fast-path markers.
5. Run only bounded synthetic lease pressure stages: 20, 50, 100, and 250 concurrent `/v1/tasks/lease` calls.
6. Verify no task is claimed by the synthetic probe and no full MIMO, FormulaLM, or worker wave is started.
7. Verify post-canary health routes, resource counters, and service logs.
8. Create exact run artifacts, run repository checks, commit, and push the branch.

