# Actions

Snapshot: 2026-07-02T12:45:56Z

Changed:

- `ops/factory_control.py`
- `tests/test_factory_runtime.py`

Implementation:

- Added `DEFAULT_MIMO_TASK_KINDS`.
- Added `task_envelope_value(...)` so compatibility can read task-level or
  envelope-level routing fields.
- Added `effective_task_runner(...)`.
- Updated `compatible(...)` to require runner capability for effective runner.
- Added tests for implicit MIMO runner, missing runner capability, and MIMO
  Pool `target_node` pinning.

No production deploy, service restart, main merge, credential mutation, queue
deletion or full MIMO wave was performed.

