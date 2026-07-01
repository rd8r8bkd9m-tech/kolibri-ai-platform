# PR #91 MIMO Runner Output/Auth Contract Repair Next

Task ID: `P0_MIMO_RUNNER_OUTPUT_AND_AUTH_CONTRACT_REPAIR_2026_07_01`

1. Publish this artifact hygiene cleanup to branch `p0/mimo-runner-output-auth-contract-repair-2026-07-01` with a normal non-force push.
2. Confirm PR #91 no longer tracks top-level `artifacts/P0_MIMO_RUNNER_OUTPUT_AND_AUTH_CONTRACT_REPAIR_2026_07_01/*` files.
3. Merge and deploy PR #91 under the release gate once repository review policy is satisfied.
4. Canary next step: rerun direct MIMO fanout after merge/deploy.
5. Confirm the live canary covers useful JSON stdout handling, HTTP 401 `runner_auth_failed`, HTTP 403 policy/access blocker classification, and runner-specific error preservation.
