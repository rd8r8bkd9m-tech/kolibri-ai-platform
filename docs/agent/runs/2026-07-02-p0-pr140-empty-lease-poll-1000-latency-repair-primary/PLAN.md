# PLAN

Scope: stacked repair on top of PR #140 head `56234301568507b2fd8b45d59e7a1c5cf69625e2`.

1. Preserve PR #140's hard 64 HTTP worker cap and non-blocking accept-loop executor submission.
2. Remove remaining Redis work from warmed empty `/v1/tasks/lease` bursts.
3. Keep task creation and queued-task recovery correct by invalidating the empty fast path on enqueue or queued task save.
4. Add regression tests for 500 concurrent empty lease polls and cache invalidation.
5. Do not merge.
6. Do not deploy runtime from this implementation task.
