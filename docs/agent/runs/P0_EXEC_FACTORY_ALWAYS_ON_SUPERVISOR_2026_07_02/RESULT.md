# Result

Status: `pushed_pr_branch`

Pushed branch:

`agent/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/generic-v2`

PR creation URL:

`https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/new/agent/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/generic-v2`

What now works:

- `kolibri-factory-control` can run a 24/7 supervisor loop in-process.
- The loop checks Redis health, node freshness, expired leases, and stuck task heartbeats.
- Dead agents are marked and receive scoped `repair_dead_agent` tasks.
- Repair dispatch is capped to at most 50% of registered nodes per cycle.
- Stuck leased/running/review tasks are requeued while retry budget remains, otherwise moved to dead letter.
- Owner-facing supervisor status includes `owner_summary_ru` in Russian.
- `GET /v1/factory/supervisor` provides a read-only status snapshot.
- `POST /v1/factory/supervisor/run` runs one scoped cycle when enabled.
- `FACTORY_SUPERVISOR_ENABLED=0` disables mutating supervisor behavior.

Changed files:

- `ops/factory_control.py`
- `tests/test_factory_supervisor_loop.py`
- `docs/agent/runs/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/PLAN.md`
- `docs/agent/runs/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/ACTIONS.md`
- `docs/agent/runs/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/TESTS.md`
- `docs/agent/runs/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/RESULT.md`
- `docs/agent/runs/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/NEXT.md`

Verification:

- `python3 -m py_compile ops/factory_control.py`
- `python3 -m pytest tests/test_factory_supervisor_loop.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_control_runtime_import_path.py`
- `python3 -m pytest tests` was attempted and blocked during collection because `httpx` is not installed in the local Python environment.

Blocked:

- Not deployed to the live server from this worktree.
- Full repository pytest is blocked until backend requirements are installed locally.

Exact repair command for the test environment:

```bash
python3 -m pip install -r backend/requirements.txt
```

Rollback:

```bash
FACTORY_SUPERVISOR_ENABLED=0 systemctl restart kolibri-factory-control.service
```

Risk:

- The supervisor creates repair tasks automatically for dead nodes, so rollout should begin with a live status check and the default 50% cap.
- A single-node fleet has a repair budget of `0` by design, because dispatching one repair would exceed the 50% cap.
