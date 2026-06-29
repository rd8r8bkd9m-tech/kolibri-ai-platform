# Control Plane API P0 report

Date: 2026-06-29
Role: Control Plane API engineer
Scope: local code patch and contract validation only. No Redis, live Control
Plane mutations, leases, drains, retries, task submissions, SSH, FormulaLM, or
LLM/model workloads were run from this Mac.

## Context read

- `ops/factory_control.py` keeps task and node state in Redis and exposes
  `/v1/tasks`, `/v1/tasks/lease`, task lifecycle endpoints, node registration,
  heartbeat, drain, and agent messages.
- `ops/agent_host.py` registers nodes, heartbeats active tasks, leases through
  `/v1/tasks/lease`, refreshes leases while running commands, and completes or
  fails tasks back into the Control Plane.
- `docs/agent-work/control-plane-queue-unblock-report.md` records the live P0
  symptom: broad `/v1/tasks?summary=1&compact=1` reads were too large and
  misleading; `limit` could make queue depth look smaller than reality.
- `docs/agent-work/ubuntu-qa-runner-report.md` repeats the operational rule:
  avoid broad `/v1/tasks` as a required health step until compact summary is
  fixed; use targeted `/v1/tasks/<task_id>` when necessary.

## Patch

Changed `ops/factory_control.py` to make `/v1/tasks?summary=1&compact=1&limit=N`
bounded and observable:

- Added configurable bounds:
  - `FACTORY_DEFAULT_TASK_LIST_LIMIT`, default `200`.
  - `FACTORY_MAX_TASK_LIST_LIMIT`, default `500`.
  - `FACTORY_MAX_TASK_SUMMARY_SCAN`, default `2000`.
  - `FACTORY_LEASE_EXPIRING_SOON_SECONDS`, default `30`.
- Added Redis `LLEN`-based `queue_length()` so queue depth does not require
  returning the whole queue.
- Added `queue_prefix(limit)` so the API returns only an inspectable queue
  prefix while preserving `queue_total`, `queue_returned`, and
  `queue_truncated`.
- Added bounded task sampling and compact listing for the compact summary path.
  Returned task items use `compact_task()` and do not include large `envelope`
  or `result` payloads.
- Added summary lease counters:
  - `active_total`;
  - `expired_lease_total`;
  - `lease_expiring_soon_total`.
- Added response metadata:
  - `tasks_scanned`, `tasks_matched`, `tasks_returned`;
  - `tasks_truncated`, `scan_truncated`;
  - `limit`, `max_limit`, `summary_scope`.

The compact summary response now exposes queue/lease health without emitting a
full task dump. Non-summary list responses also return a bounded queue prefix
instead of `LRANGE queue 0 -1`.

## Contract test

Added `tests/test_factory_runtime_queue_contracts.py` coverage for compact task
listing. The test monkeypatches Redis-facing functions and verifies that:

- `limit=1` returns one compact task;
- returned tasks omit `envelope` and `result`;
- queue depth remains visible through `queue_length` / `queue_total`;
- queue and task truncation are explicit;
- expired running leases are counted.

## Validation

Passed:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile ops/factory_control.py ops/agent_host.py
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
# Import ops/factory_control.py, monkeypatch Redis-facing functions, and assert
# compact_task_listing bounds payload while exposing queue/lease counters.
PY
```

The one-off harness printed:

```text
compact_task_listing harness passed
```

Blocked:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_factory_autonomy_contracts.py
```

The current system Python is `/opt/homebrew/opt/python@3.14/bin/python3.14` and
does not have `pytest` installed: `No module named pytest`.

## Risks and follow-ups

- State and lease counts are computed from a bounded scan of Redis task ids, not
  from maintained Redis secondary indexes. This prevents runaway responses, but
  very large deployments may need indexed state counters for exact global
  counts.
- `summary_scope=bounded_scan` is explicit. Operators should treat
  `scan_truncated=true` as a signal that totals are partial.
- This patch is read-only for listing endpoints. It does not change lease
  requeue behavior or perform any live stale-lease surgery.
- Existing uncommitted work was present in `ops/factory_control.py` before this
  patch, including agent message endpoints. This P0 change was layered on top
  without reverting that parallel work.
