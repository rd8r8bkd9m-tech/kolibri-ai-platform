# HTTP TAIL LATENCY REPAIR

Strict live canary still failed after PR #141/`656e07e` with empty-poll transport status `0` at stage250=20 and stage500=62. PR #141 had already reduced Redis work, so this follow-up removes two remaining per-request HTTP costs on the hot empty lease path.

Repair points:

- Empty `200/no_task` lease responses now use compact JSON bytes instead of per-request pretty-print `json.dumps(..., indent=2)`.
- The no-task bytes are cached for the stable response contract values used by the lease poll loop.
- Successful `/v1/tasks/lease` access logs are suppressed by default to avoid stderr write contention during empty-poll bursts.
- `FACTORY_LEASE_POLL_ACCESS_LOGS=1` restores successful lease-poll access logs when needed for diagnostics.

Contract:

- Response status remains `200`.
- JSON body fields remain unchanged: `status`, `task`, `reason`, `detail`, `retry_after_seconds`, and `lease_queue_scan_limit`.
- Error and non-2xx request logs remain visible.
- No runtime deployment was performed from this implementation task.
