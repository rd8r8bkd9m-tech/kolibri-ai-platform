# PR #83 Review PR Read-Only Diff Contract Repair Tests

Task ID: `P0_PR83_REVIEW_PR_READ_ONLY_DIFF_CONTRACT_REPAIR_2026_07_01`

## Passed

- `python3 -m pytest -q tests/test_agent_host_runner_contract.py`
  - Result: passed, `29 passed in 34.68s`.
- `python3 -m pytest -q tests/test_agent_host_runner_contract.py tests/test_agent_host_image_generation.py tests/test_agent_host_telegram_chat.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py`
  - Result: passed, `43 passed in 38.80s`.
- `python3 -m py_compile ops/agent_host.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Regression Proven

`test_read_only_review_pr_separates_reviewed_diff_from_runner_changes` verifies that a read-only `review_pr` task can review a product-code PR diff (`backend/providers.py`) without falsely blocking as product-code modified by the runner. The reviewed diff is preserved in `reviewed_diff_files`, while runner-authored `changed_files` remains empty.
