# STRICT CANARY DECISION

Decision: repair_branch_ready_for_ci_and_runtime_canary

Evidence before this repair:

- PR #141 live strict canary failed after deployment at stage250/stage500 empty lease polls with transport status 0.
- Created tasks still matched leased tasks, so the remaining failure class is HTTP tail latency/transport pressure, not task loss.

Repair in this branch:

- Compact pre-encoded no-task JSON bytes for hot empty lease responses.
- Successful /v1/tasks/lease access-log suppression by default, with FACTORY_LEASE_POLL_ACCESS_LOGS opt-in for diagnostics.

Verification on primary-candidate implementation worktree:

- python3 -m pytest tests/test_factory_capacity_controls.py -q -> 24 passed
- python3 -m py_compile ops/factory_control.py -> passed
- python3 -m pytest tests/test_factory_capacity_controls.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_control_runtime_import_path.py tests/test_factory_control_superfactory.py -q -> 44 passed
- bash scripts/preflight-factory-control-runtime.sh -> factory_control_runtime_preflight=ok

Next gate:

- Push branch, run CI, then deploy to primary-candidate with backup and run strict 20/50/100/250/500/1000 live canary.
- Merge/deploy PR #119 remains blocked until strict canary has zero transport status 0/5xx and created_tasks == leased_tasks through 1000.
