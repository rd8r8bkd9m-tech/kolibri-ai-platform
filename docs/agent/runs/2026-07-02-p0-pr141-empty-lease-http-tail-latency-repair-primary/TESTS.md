# TESTS

Passed on primary-candidate implementation worktree:

- `python3 -m pytest tests/test_factory_capacity_controls.py -q` -> `24 passed in 6.30s`
- `python3 -m py_compile ops/factory_control.py` -> passed

Regression coverage added:

- `test_empty_lease_no_task_response_is_preencoded_compact_json`
- `test_successful_lease_poll_access_logs_are_suppressed_by_default`

Notes:

- `python` is not installed in this environment; verification used `python3`.
- Runtime canary was not run.
- Runtime deployment was not performed.
