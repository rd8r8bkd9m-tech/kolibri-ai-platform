# RUNNING_INDEX_DRIFT.md

**Date:** 2026-07-04T22:00:00Z

## Finding
State index shows running=12 but active summary shows active_total=0.

## Root Cause
Tasks completed/failed but running index not decremented. Phantom running state.

## Recommended Action
Create P0_QUEUE_RUNNING_INDEX_REBUILD_WITH_BACKUP_20260704 to:
1. Export current task state
2. Reconcile running index with actual task states
3. Reset phantom running tasks to their actual terminal states
