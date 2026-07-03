# Result

Implemented on branch `codex/p0-fabric-route-target-lookup-exhaustive-repair-20260703t120400z`, based on PR #159 (`origin/pr/159`).

Explicit `target_node` routing now consults the authoritative node record by exact node id before applying route health and capability gates. This means a live node such as `new` can route even when it is outside the bounded fallback candidate/sample list.

Fallback candidates remain bounded with `FABRIC_ROUTE_FALLBACK_LIMIT` defaulting to 26. PR #159 health vocabulary is preserved: `fresh`, `ok`, `online`, and `running` remain routable while stale/degraded/offline/drained or missing capability stay blocked.

Verification passed:

- Focused fabric route tests: 15 passed.
- Full test suite in local venv: 172 passed, 1 warning.
