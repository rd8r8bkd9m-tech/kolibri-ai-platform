# P0 Control Plane Task Index Reconcile

Timestamp: 2026-07-03T09:00Z

Branch: `repair/task-index-reconcile-mesh06-20260703`

## Summary

Implemented task list reconciliation for `ops/factory_control.py` so `/v1/tasks` and `/v1/tasks?compact=1&summary=1` no longer depend solely on the `task_ids` set or a stale `queue_active_index`.

The list path now reconciles task ids from:

- `task_ids`
- pending queue ids
- `queue_active_index` when present as a Redis set, list, or zset
- authoritative Redis `task:*` records discovered with `SCAN`

Summary counts include fresh queued/running/review work, but terminal tasks and expired leased/running records do not inflate `active_total`.

## Changed Files

- `ops/factory_control.py`
- `tests/test_factory_runtime.py`

## Verification

Command:

```bash
python3 -m pytest tests/test_factory_runtime.py -q
```

Result:

```text
9 passed in 0.12s
```

Command:

```bash
python3 -m pytest tests/test_prompt3_fabric_api_surface.py tests/test_factory_control_superfactory.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py -q
```

Result:

```text
16 passed in 0.10s
```

Command:

```bash
python3 -m py_compile ops/factory_control.py
```

Result: passed.

Command:

```bash
git diff --check
```

Result: passed.

## Notes

No direct main push was performed. No secrets were collected or printed.
