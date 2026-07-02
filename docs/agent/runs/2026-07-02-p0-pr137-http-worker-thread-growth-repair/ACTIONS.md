# ACTIONS

- Re-attached the initially empty task worktree to PR #137 head `93df313c8d4e70ab1e051ba64854a868b8ae9338`.
- Updated `ops/factory_control.py` to clamp `FACTORY_HTTP_MAX_WORKERS` to a hard ceiling of `64`.
- Added semaphore-backed admission around the fixed HTTP executor so accepted requests wait for a worker slot instead of generating an overload/503 response.
- Preserved the existing fast empty queue `200/no_task` path.
- Updated `tests/test_factory_capacity_controls.py` with regression coverage for stale `FACTORY_HTTP_MAX_WORKERS=256` configuration.
- Did not deploy runtime.
- Did not deploy PR #119.
- Did not requeue MIMO/FormulaLM.
