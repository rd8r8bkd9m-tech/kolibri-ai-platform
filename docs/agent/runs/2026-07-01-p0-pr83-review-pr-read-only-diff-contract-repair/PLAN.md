# PR #83 Review PR Read-Only Diff Contract Repair Plan

Task ID: `P0_PR83_REVIEW_PR_READ_ONLY_DIFF_CONTRACT_REPAIR_2026_07_01`

1. Fast-forward local PR #83 branch to `origin/p0/agent-host-runner-contract-hardening-2026-06-30`.
2. Inspect `run_review_pr` and `finalize_runner_contract` to identify the contract boundary.
3. Keep reviewed PR diff paths in a review-specific result field.
4. Pass only runner-authored changed files to the runner contract finalizer.
5. Add a regression test for read-only PR review of a product-code diff.
6. Run focused Agent Host runner/review/runtime tests.
7. Publish only the PR #83 branch normally.
